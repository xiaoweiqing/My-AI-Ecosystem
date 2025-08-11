# ==============================================================================
#                      每日复盘AI (Daily Review AI) v3.8
#                      (Training Hub Integrated Edition)
# ==============================================================================
# 版本说明:
# - 【核心新增】无缝集成了“AI训练中心”模块。
# - 【自动归档】每次成功的每日复盘，都会自动将“原始数据汇总”和“AI报告”
#              作为一条“摘要生成”任务，存入您的[AI训练中心]数据库。
# - 【严格遵守】确保v3.7所有原有功能（包括超长报告切分）100%保留。
# ==============================================================================

import os
import google.generativeai as genai
from notion_client import Client, APIResponseError
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import sys
import re
import threading

def print_separator():
    print("\n" + "="*70 + "\n")

# --- 【【【 新增：移植自v9.5工具箱的核心模块 】】】 ---
def clean_text(text):
    """文本净化器，移除无效字符，确保API调用成功。"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)

def write_to_training_hub(notion, task_type, input_text, output_text, source_db_name, source_page_id, config):
    """将复盘任务作为训练数据写入“AI训练中心”数据库。"""
    training_hub_db_id = config.get("TRAINING_HUB_DB_ID")
    if not training_hub_db_id:
        print(">> [训练中心] 未配置数据库ID (TRAINING_HUB_DATABASE_ID)，跳过写入。")
        return

    try:
        # 清理并截断文本以符合Notion限制
        safe_input_text = clean_text(str(input_text))[:1990]
        safe_output_text = clean_text(str(output_text))[:1990]
        
        training_title = f"【{task_type}】{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')} 复盘摘要"
        
        properties_data = {
            "训练任务": {"title": [{"text": {"content": training_title}}]},
            "任务类型": {"select": {"name": task_type}},
            "源数据 (Input)": {"rich_text": [{"text": {"content": safe_input_text}}]},
            "理想输出 (Output)": {"rich_text": [{"text": {"content": safe_output_text}}]},
            "标注状态": {"select": {"name": "待审核"}}
        }

        # 动态处理关联列
        relation_column_map = {
            'DailyReview': config.get("RELATION_LINK_REVIEW_NAME", "源链接-每日复盘"),
        }
        
        if source_db_name in relation_column_map and source_page_id:
            column_to_update = relation_column_map[source_db_name]
            properties_data[column_to_update] = {"relation": [{"id": source_page_id}]}
        
        notion.pages.create(parent={"database_id": training_hub_db_id}, properties=properties_data)
        print(f">> [训练中心] 已成功记录一条 '{task_type}' 训练数据。")

    except Exception as e:
        print(f"!! [训练中心] 写入时出错: {e}")

# --- 1. 初始化与配置加载 (已升级) ---
def initialize():
    """加载配置并初始化所有服务"""
    print_separator()
    print("🚀 启动每日复盘AI引擎 (v3.8 - Training Hub Integrated)...")
    load_dotenv()
    config = {
        "NOTION_TOKEN": os.getenv("NOTION_API_KEY"),
        "API_KEY": os.getenv("GEMINI_API_KEY"),
        "LOG_DB_ID": os.getenv("TOOLBOX_LOG_DATABASE_ID"),
        "BRAIN_DB_ID": os.getenv("CORE_BRAIN_DATABASE_ID"),
        "CANDIDATE_DB_ID": os.getenv("CANDIDATE_DATABASE_ID"),
        "REVIEW_DB_ID": os.getenv("DAILY_REVIEW_DATABASE_ID"),
        # --- 【【【 新增配置项 】】】 ---
        "TRAINING_HUB_DB_ID": os.getenv("TRAINING_HUB_DATABASE_ID"),
        "RELATION_LINK_REVIEW_NAME": os.getenv("RELATION_LINK_REVIEW_NAME", "源链接-每日复盘") # 允许在.env中自定义列名
    }
    if not all([config["NOTION_TOKEN"], config["API_KEY"], config["REVIEW_DB_ID"]]):
        print("❌ 错误：关键配置缺失！(NOTION_API_KEY, GEMINI_API_KEY, DAILY_REVIEW_DATABASE_ID 必须在 .env 文件中配置)")
        sys.exit(1)
    try:
        notion = Client(auth=config["NOTION_TOKEN"])
        genai.configure(api_key=config["API_KEY"])
        gemini_model = genai.GenerativeModel('models/gemini-2.5-pro') 
        print("✅ Notion 和 Gemini API 初始化成功！")
        return notion, gemini_model, config
    except Exception as e:
        print(f"❌ 初始化失败: {e}"); sys.exit(1)

# --- 2. 从Notion拉取当日数据 (原样保留 v3.7) ---
def fetch_todays_data(notion, db_id, db_name):
    if not db_id:
        print(f"🟡 跳过 [{db_name}]：未在.env中配置其数据库ID。"); return ""
    print(f"⏳ 正在从 [{db_name}] 数据库拉取今日数据...")
    today_utc = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        response = notion.databases.query(database_id=db_id, filter={"timestamp": "last_edited_time", "last_edited_time": {"on_or_after": today_utc.isoformat()}})
        pages = response.get("results", [])
        if not pages:
            print(f"  - 在 [{db_name}] 中未发现今日更新。"); return ""
        content_list = []
        for page in pages:
            title, properties = "[无标题]", page.get("properties", {})
            title_prop_names = ["主题", "日志标题 名称", "候选人姓名"]
            for prop_name in title_prop_names:
                if prop_name in properties and properties[prop_name].get("type") == "title":
                    title_parts = properties[prop_name].get("title", [])
                    if title_parts: title = title_parts[0].get("plain_text", "[空标题]"); break
            page_summary = f"\n--- 记录来源: {db_name} | 标题: {title} ---\n"
            if db_name == "AI候选人分析中心":
                reason_prop = properties.get("评分理由", {}).get("rich_text", [])
                if reason_prop: page_summary += f"核心评价: {reason_prop[0].get('plain_text', '')}\n"
            else: 
                try:
                    blocks_response = notion.blocks.children.list(block_id=page["id"], page_size=10)
                    for block in blocks_response.get("results", []):
                        if "paragraph" in block and "rich_text" in block["paragraph"]:
                            for text_part in block["paragraph"]["rich_text"]: page_summary += text_part.get("plain_text", "") + "\n"
                except APIResponseError: page_summary += "[无法获取页面正文]\n"
            content_list.append(page_summary)
        print(f"  - 成功从 [{db_name}] 拉取 {len(pages)} 条记录。")
        return "\n".join(content_list)
    except APIResponseError as e:
        print(f"❌ 查询 [{db_name}] 时出错: {e}"); return ""

# --- 3. 调用AI进行分析 (原样保留 v3.7) ---
def analyze_and_generate_report(gemini_model, daily_data_text):
    print("🧠 正在调用AI进行深度战略分析与规划...")
    print("   (数据已发送给Google，设定3分钟超时限制，请耐心等待)...")
    prompt = f"""
# 角色与任务
你是一位顶级的战略顾问。基于我提供的【今日工作数据汇总】，完成两项任务：
1.  生成一份详细的“每日战略复盘与未来规划报告”。
2.  提炼出一个极其精炼的“行动指针”总结。

# 待分析数据
---
【今日工作数据汇总】
{daily_data_text}
---

# 输出指令与格式
你必须严格按照以下格式输出，分为【报告主体】和【行动指针】两部分。

### 第1部分：报告主体
请使用以下Markdown格式生成报告。
---
## 每日战略复盘与未来规划 - {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')}
### 1. 今日核心成果概览 (Executive Summary)
*   **[用2-3个要点，概括核心产出与活动]**
### 2. 亮点与高光时刻 (Key Achievements & Highlights)
*   **[识别并阐述1-2件最有价值的事及其战略意义]**
### 3. 瓶颈与潜在风险分析 (Bottlenecks & Potential Risks)
*   **[分析效率瓶颈、重复劳动或潜在风险]**
### 4. 具体流程改进建议 (Process Improvement Suggestions)
*   **关于招聘流程:** [提出具体改进措施]
*   **关于知识管理:** [提出具体改进措施]
*   **关于AI工具链:** [提出具体改进措施]
### 5. 宏观洞察与未来方向 (Macro-Level Insights & Future Directions)
*   **浮现的主题:** [发现新的战略重点]
*   **跨领域连接:** [发现不同工作间的关联]
*   **新项目/新AI孵化建议:** [提出新的项目点子]
### 6. 明日核心优先事项 (Top Priorities for Tomorrow)
- [ ] **[生成2-3个最重要的待办事项]**
- [ ] **[第二个待办事项]**
---

### 第2部分：行动指针
在报告主体之后，你必须另起一行，提供一个被 `<SUMMARY>` 和 `</SUMMARY>` 标签包裹的、不超过两句话的行动指针。这个指针要高度浓缩报告中最核心的、最需要我关注的行动建议。
【示例】: `<SUMMARY>明日应优先系统化整理今日关于XX技术的零散笔记，并基于此调整招聘JD的关键词以吸引更精准的候选人。</SUMMARY>`
"""
    try:
        response = gemini_model.generate_content(prompt, request_options={"timeout": 180})
        report_text = response.text
        print("✅ AI战略分析完成，高级报告已生成！")
        return report_text
    except Exception as e:
        print(f"❌ AI分析时出错！程序中断。 错误详情: {e}"); return None

# --- 4. 将报告保存回Notion (已升级) ---
def save_report_to_notion(notion, config, report_text, original_data):
    """将报告保存到Notion，并【触发】保存训练数据到AI训练中心。"""
    review_db_id = config["REVIEW_DB_ID"]
    print("✍️ 正在将复盘报告保存到'每日工作日志'数据库...")
    summary, main_report = "", report_text
    start_tag, end_tag = "<SUMMARY>", "</SUMMARY>"
    start_index, end_index = report_text.find(start_tag), report_text.find(end_tag, report_text.find(start_tag))
    
    if start_index != -1 and end_index != -1:
        summary = report_text[start_index + len(start_tag):end_index].strip()
        main_report = report_text[:start_index].strip()
        print(f"  - 已成功提取行动指针: {summary}")
    else:
        print("  - 未在AI响应中找到行动指针标签，该列将为空。")
        main_report = report_text # 如果没有标签，整个文本都是报告主体

    try:
        beijing_time = datetime.now(timezone(timedelta(hours=8)))
        today_str, today_iso = beijing_time.strftime('%Y-%m-%d'), beijing_time.isoformat()
        
        properties_data = {
            "日志标题 名称": {"title": [{"text": {"content": f"{today_str} AI战略复盘报告"}}]},
            "日期": {"date": {"start": today_iso}},
            "条目类型": {"select": {"name": "AI复盘报告"}},
            "本日状态工作状态": {"select": {"name": "已完成"}},
        }
        if summary:
            properties_data["行动指针"] = {"rich_text": [{"text": {"content": summary}}]}
        
        # v3.7 终极完美修复 (原样保留)
        children_blocks = [{
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
                "icon": {"emoji": "🎯" if i == 0 else "📄"},
                "color": "default"
            }
        } for i, chunk in enumerate([main_report[i:i + 1990] for i in range(0, len(main_report), 1990)])]

        # --- 【【【 核心改动点 】】】 ---
        # 1. 创建页面，并接收返回的页面对象
        new_page = notion.pages.create(parent={"database_id": review_db_id}, properties=properties_data, children=children_blocks)
        print("🎉 每日战略复盘报告已成功保存到Notion！")

        # 2. 从返回对象中获取新页面的ID
        new_page_id = new_page.get('id')
        
        # 3. 如果成功获取ID，则在后台线程中调用写入训练中心的功能
        if new_page_id:
            print(">> 正在启动后台任务，将本次复盘存入 [AI训练中心] ...")
            threading.Thread(
                target=write_to_training_hub,
                args=(
                    notion, "摘要生成", original_data, main_report, 
                    'DailyReview', new_page_id, config
                ),
                daemon=True
            ).start()
        # --- 【【【 改动结束 】】】 ---

    except APIResponseError as e:
        print(f"❌ 保存到Notion失败: {e.code} - {e.body}")
    except Exception as e:
        print(f"❌ 保存到Notion时发生未知错误: {e}")

# --- 主程序入口 (已升级) ---
if __name__ == "__main__":
    notion, gemini_model, config = initialize()
    
    log_data = fetch_todays_data(notion, config["LOG_DB_ID"], "AI互动日志")
    brain_data = fetch_todays_data(notion, config["BRAIN_DB_ID"], "AI作战指挥室")
    candidate_data = fetch_todays_data(notion, config["CANDIDATE_DB_ID"], "AI候选人分析中心")
    
    full_daily_data = (f"--- 数据来源: AI互动日志 ---\n{log_data}\n\n"
                       f"--- 数据来源: AI作战指挥室 ---\n{brain_data}\n\n"
                       f"--- 数据来源: AI候选人分析中心 ---\n{candidate_data}")
                       
    if len(full_daily_data.strip()) < 150: 
        print("\n🟡 今日核心数据库无足够数据可供分析，程序退出。")
    else:
        final_report_with_summary = analyze_and_generate_report(gemini_model, full_daily_data)
        if final_report_with_summary:
            # 【升级】将原始数据也传入，以便写入训练中心
            save_report_to_notion(notion, config, final_report_with_summary, full_daily_data)
            
    print_separator()
    input("所有任务已完成，请按回车键退出。")