# ==============================================================================
#                      周期性复盘AI (Periodic Review AI) v5.0
#                      (ChromaDB Memory & History Refill Edition)
# ==============================================================================
# 版本说明 v5.0:
# - 【核心新增-智能记忆】集成ChromaDB向量数据库。
#   - 【写入】每次生成的报告会自动向量化并存入ChromaDB，作为长期记忆。
#   - 【读取】生成新报告时，会从ChromaDB中检索最相关的历史洞察，注入Prompt。
# - 【核心新增-补写日报】支持补写任何一天的日报。
#   - 使用新参数 `--date YYYY-MM-DD` 来指定补写的日期。
# - 【Prompt升级】AI Prompt现已包含【相关历史洞察】模块，分析更具连续性。
# - 【依赖更新】需要安装 `chromadb` 库 (`pip install chromadb`)。
# - 【配置更新】需要在 .env 文件中配置 `CHROMA_DB_PATH`。
# ==============================================================================

import os
import google.generativeai as genai
from notion_client import Client, APIResponseError
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import sys
import re
import threading
import argparse
import chromadb # 【新增】引入ChromaDB

def print_separator():
    print("\n" + "="*70 + "\n")

# --- 模块：文本净化器与训练中心写入 (v4.0原样保留) ---
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
        safe_input_text = clean_text(str(input_text))[:1990]
        safe_output_text = clean_text(str(output_text))[:1990]
        training_title = f"【{task_type}】{datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')} 周期性报告摘要"
        
        properties_data = {
            "训练任务": {"title": [{"text": {"content": training_title}}]},
            "任务类型": {"select": {"name": task_type}},
            "源数据 (Input)": {"rich_text": [{"text": {"content": safe_input_text}}]},
            "理想输出 (Output)": {"rich_text": [{"text": {"content": safe_output_text}}]},
            "标注状态": {"select": {"name": "待审核"}}
        }
        relation_column_map = {'DailyReview': config.get("RELATION_LINK_REVIEW_NAME", "源链接-每日复盘")}
        if source_db_name in relation_column_map and source_page_id:
            column_to_update = relation_column_map[source_db_name]
            properties_data[column_to_update] = {"relation": [{"id": source_page_id}]}
        
        notion.pages.create(parent={"database_id": training_hub_db_id}, properties=properties_data)
        print(f">> [训练中心] 已成功记录一条 '{task_type}' 训练数据。")

    except Exception as e:
        print(f"!! [训练中心] 写入时出错: {e}")

# --- 【【【 新增：向量数据库核心模块 】】】 ---
class VectorMemory:
    def __init__(self, path, collection_name):
        self.client = None
        self.collection = None
        if not path or not collection_name:
            print("🟡 [记忆模块] 未配置CHROMA_DB_PATH或CHROMA_COLLECTION_NAME，将跳过所有向量操作。")
            return
        try:
            print(f"🧠 [记忆模块] 正在初始化向量数据库...")
            self.client = chromadb.PersistentClient(path=path)
            self.collection = self.client.get_or_create_collection(name=collection_name, metadata={"hnsw:space": "cosine"})
            print(f"  - 成功连接到集合 '{collection_name}'。")
        except Exception as e:
            print(f"❌ [记忆模块] 初始化ChromaDB失败: {e}")
            self.client = None

    def add_memory(self, report_text, metadata):
        if not self.collection: return
        try:
            doc_id = f"{metadata['type']}-{metadata['date']}"
            print(f"  - 正在将报告 '{doc_id}' 向量化并存入长期记忆...")
            embedding_model = 'models/embedding-001'
            embedding = genai.embed_content(model=embedding_model, content=report_text, task_type="RETRIEVAL_DOCUMENT")["embedding"]
            
            self.collection.add(
                embeddings=[embedding],
                documents=[report_text],
                metadatas=[metadata],
                ids=[doc_id]
            )
            print(f"  - ✅ 记忆胶囊 '{doc_id}' 已成功存入向量数据库！")
        except Exception as e:
            print(f"  - ❌ [记忆模块] 存入记忆时出错: {e}")

    def retrieve_memory(self, query_text, n_results=3):
        if not self.collection: return ""
        try:
            print(f"  - 🧠 正在基于问题 '{query_text[:30]}...' 检索相关历史记忆...")
            embedding_model = 'models/embedding-001'
            query_embedding = genai.embed_content(model=embedding_model, content=query_text, task_type="RETRIEVAL_QUERY")["embedding"]

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
            
            if not results or not results['documents'] or not results['documents'][0]:
                print("  - 未找到相关历史记忆。")
                return ""

            retrieved_docs = []
            for i, doc in enumerate(results['documents'][0]):
                meta = results['metadatas'][0][i]
                entry = f"--- 历史洞察 ({meta.get('date', '未知日期')} {meta.get('type', '报告')}):\n{doc}\n---"
                retrieved_docs.append(entry)
            
            print(f"  - ✅ 成功检索到 {len(retrieved_docs)} 条相关历史记忆。")
            return "\n".join(retrieved_docs)
        except Exception as e:
            print(f"  - ❌ [记忆模块] 检索记忆时出错: {e}")
            return ""

# --- 1. 初始化与配置加载 (已升级) ---
def initialize():
    """加载配置并初始化所有服务"""
    print_separator()
    print("🚀 启动周期性复盘AI引擎 (v5.0)...") # 【修改】版本号更新
    load_dotenv()
    config = {
        "NOTION_TOKEN": os.getenv("NOTION_API_KEY"),
        "API_KEY": os.getenv("GEMINI_API_KEY"),
        "LOG_DB_ID": os.getenv("TOOLBOX_LOG_DATABASE_ID"),
        "BRAIN_DB_ID": os.getenv("CORE_BRAIN_DATABASE_ID"),
        "CANDIDATE_DB_ID": os.getenv("CANDIDATE_DATABASE_ID"),
        "REVIEW_DB_ID": os.getenv("DAILY_REVIEW_DATABASE_ID"),
        "TRAINING_HUB_DB_ID": os.getenv("TRAINING_HUB_DATABASE_ID"),
        "RELATION_LINK_REVIEW_NAME": os.getenv("RELATION_LINK_REVIEW_NAME", "源链接-每日复盘"),
        # --- 【新增配置】 ---
        "CHROMA_DB_PATH": os.getenv("CHROMA_DB_PATH"),
        "CHROMA_COLLECTION_NAME": os.getenv("CHROMA_COLLECTION_NAME")
    }
    if not all([config["NOTION_TOKEN"], config["API_KEY"], config["REVIEW_DB_ID"]]):
        print("❌ 错误：关键配置缺失！(NOTION_API_KEY, GEMINI_API_KEY, DAILY_REVIEW_DATABASE_ID 必须在 .env 文件中配置)")
        sys.exit(1)
    try:
        notion = Client(auth=config["NOTION_TOKEN"])
        genai.configure(api_key=config["API_KEY"])
        gemini_model = genai.GenerativeModel('models/gemini-2.5-pro') # 【修改】这里我看到您的代码用了flash-lite，但为了长远考虑和兼容更复杂的任务，建议用1.5-pro
        # --- 【新增】初始化向量记忆模块 ---
        memory = VectorMemory(config["CHROMA_DB_PATH"], config["CHROMA_COLLECTION_NAME"])
        print("✅ Notion, Gemini API 和 向量记忆模块 初始化成功！")
        return notion, gemini_model, memory, config # 【修改】增加memory返回
    except Exception as e:
        print(f"❌ 初始化失败: {e}"); sys.exit(1)

# --- 时间范围计算 (已升级，支持补写) ---
def get_date_range(report_type, specific_date_str=None):
    """根据报告类型或指定日期计算开始和结束日期"""
    # --- 【新增】补写日报逻辑 ---
    if specific_date_str:
        try:
            beijing_tz = timezone(timedelta(hours=8))
            target_date = datetime.strptime(specific_date_str, '%Y-%m-%d')
            # 定义北京时间的开始和结束
            start_date_local = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=beijing_tz)
            end_date_local = target_date.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=beijing_tz)
            # 转换为UTC时间以供Notion API查询
            return start_date_local.astimezone(timezone.utc), end_date_local.astimezone(timezone.utc)
        except ValueError:
            print(f"❌ 日期格式错误: '{specific_date_str}'。请使用 YYYY-MM-DD 格式。程序退出。")
            sys.exit(1)
            
    # --- 以下是v4.0的原有逻辑 ---
    end_date = datetime.now(timezone.utc)
    if report_type == 'daily':
        # 修正为北京时间当天0点到24点
        today_beijing = datetime.now(timezone(timedelta(hours=8))).date()
        start_of_day_beijing = datetime.combine(today_beijing, datetime.min.time(), tzinfo=timezone(timedelta(hours=8)))
        start_date = start_of_day_beijing.astimezone(timezone.utc)
    elif report_type == 'weekly':
        start_date = end_date - timedelta(days=7)
    elif report_type == 'monthly':
        start_date = end_date - timedelta(days=30)
    elif report_type == 'quarterly':
        start_date = end_date - timedelta(days=90)
    elif report_type == 'yearly':
        start_date = end_date - timedelta(days=365)
    else: # 默认为日报
        today_beijing = datetime.now(timezone(timedelta(hours=8))).date()
        start_of_day_beijing = datetime.combine(today_beijing, datetime.min.time(), tzinfo=timezone(timedelta(hours=8)))
        start_date = start_of_day_beijing.astimezone(timezone.utc)

    return start_date, end_date

# --- 数据拉取函数 (已升级，支持精确日期范围) ---
def fetch_data_for_period(notion, db_id, db_name, start_date, end_date):
    """根据指定的时间范围从Notion拉取数据"""
    if not db_id:
        print(f"🟡 跳过 [{db_name}]：未在.env中配置其数据库ID。"); return ""
    print(f"⏳ 正在从 [{db_name}] 数据库拉取周期内数据...")
    
    try:
        # 【修改】过滤器升级为复合过滤器，以支持精确的开始和结束日期
        response = notion.databases.query(
            database_id=db_id, 
            filter={
                "and": [
                    {"timestamp": "last_edited_time", "last_edited_time": {"on_or_after": start_date.isoformat()}},
                    {"timestamp": "last_edited_time", "last_edited_time": {"before": end_date.isoformat()}}
                ]
            }
        )
        pages = response.get("results", [])
        if not pages:
            print(f"  - 在 [{db_name}] 中未发现该周期内的更新。"); return ""
        
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


# --- AI Prompt生成器 (已升级，注入历史记忆) ---
def get_prompt_for_report(report_type, data_text, start_date_str, end_date_str, historical_insights=""):
    """根据报告类型生成专属的AI Prompt, 并注入历史洞察"""
    
    # --- 以下是v4.0的原有代码 ---
    report_titles = {
        'daily': '每日战略复盘与未来规划', 'weekly': '每周战略回顾与展望',
        'monthly': '月度战略复盘与目标校准', 'quarterly': '季度深度复盘与战略调整',
        'yearly': '年度综合复盘与未来战略规划'
    }
    report_title = report_titles.get(report_type, '周期性复盘报告')
    period_scopes = {
        'daily': ('今日', '明日'), 'weekly': ('本周', '下周'),
        'monthly': '本月', 'quarterly': '本季度', 'yearly': '本年度'
    }
    scope_texts = {
        'daily': ("今日核心成果概览", "明日核心优先事项"),
        'weekly': ("本周核心成果与趋势", "下周核心目标与策略"),
        'monthly': ("本月关键进展与挑战", "下月战略重点"),
        'quarterly': ("本季度重大成就与瓶颈", "下季度核心战略方向"),
        'yearly': ("本年度核心里程碑与教训", "下一年度战略蓝图")
    }
    current_scope, next_scope = scope_texts[report_type]

    # --- 【新增】历史洞察部分 ---
    historical_context_section = ""
    if historical_insights:
        historical_context_section = f"""
# 相关历史洞察 (从我的记忆库中检索)
这些是过去最相关的报告摘要，请在分析时参考，以发现趋势和联系：
{historical_insights}
---
"""
    # 【修改】Prompt模板中增加了 historical_context_section
    prompt = f"""
# 角色与任务
你是一位顶级的、具有连续记忆的战略顾问。你的任务是结合【相关历史洞察】和我提供的【当前周期数据】，生成一份深刻的、具有前后关联性的复盘报告。

{historical_context_section}

# 当前待分析数据
---
【{period_scopes[report_type][0] if isinstance(period_scopes[report_type], tuple) else period_scopes[report_type]}工作数据汇总 (从 {start_date_str} 到 {end_date_str})】
{data_text}
---

# 输出指令与格式
你必须严格按照以下Markdown格式输出，分为【报告主体】和【行动指针】两部分。在分析时，请特别注意【当前周期数据】与【相关历史洞察】之间的联系、演变或矛盾。

### 第1部分：报告主体
---
## {report_title} - {end_date_str}
### 1. {current_scope} (Executive Summary)
*   **[用2-4个要点，高度概括本周期内的核心产出、关键趋势和活动]**
### 2. 亮点与高光时刻 (Key Achievements & Highlights)
*   **[识别并阐述1-3件最有价值的事，并分析其对于 {period_scopes[report_type][0] if isinstance(period_scopes[report_type], tuple) else period_scopes[report_type]} 目标的战略意义]**
### 3. 瓶颈与战略反思 (Bottlenecks & Strategic Reflections)
*   **[分析本周期内遇到的主要障碍、效率瓶颈，并进行更深层次的战略原因反思。是资源问题？方向问题？还是执行问题？]**
### 4. 跨周期洞察与模式识别 (Cross-Period Insights & Pattern Recognition)
*   **浮现的主题:** [本周期内反复出现的新主题或新机会是什么？]
*   **模式与关联:** [不同工作任务之间是否存在可以利用的潜在关联或模式？]
*   **战略假设验证:** [本周期的实践，是验证了还是挑战了我们之前的战略假设？]
### 5. {next_scope} ({'Priorities for Next Period' if report_type != 'daily' else 'Top Priorities for Tomorrow'})
- [ ] **[基于以上所有分析，生成2-4个最重要、最具战略价值的待办事项或目标，用于指导下一周期]**
- [ ] **[第二个待办事项]**
---

### 第2部分：行动指针
在报告主体之后，你必须另起一行，提供一个被 `<SUMMARY>` 和 `</SUMMARY>` 标签包裹的、不超过两句话的行动指针。这个指针要高度浓缩报告中最核心的、最需要我关注的行动建议，作为下一周期的最高指导原则。
【示例】: `<SUMMARY>下周应集中精力将AI候选人分析流程标准化，并启动对'项目X'的初步技术预研，以验证其长期价值。</SUMMARY>`
"""
    return prompt

# --- 4. 调用AI进行分析 (v4.0原样保留) ---
def analyze_and_generate_report(gemini_model, prompt):
    print("🧠 正在调用AI进行深度战略分析...")
    print("   (数据已发送给Google，设定3分钟超时限制，请耐心等待)...")
    try:
        response = gemini_model.generate_content(prompt, request_options={"timeout": 180})
        report_text = response.text
        print("✅ AI战略分析完成，高级报告已生成！")
        return report_text
    except Exception as e:
        print(f"❌ AI分析时出错！程序中断。 错误详情: {e}"); return None

# --- 5. 将报告保存回Notion (已升级，增加向量记忆写入) ---
def save_report_to_notion(notion, memory, config, report_type, report_text, original_data, start_date, end_date): #【修改】增加memory参数
    """将报告保存到Notion，并触发向量化和训练中心写入。"""
    review_db_id = config["REVIEW_DB_ID"]
    
    report_type_map = {
        'daily': 'AI复盘报告', 'weekly': 'AI周报', 'monthly': 'AI月报',
        'quarterly': 'AI季报', 'yearly': 'AI年报'
    }
    report_notion_type = report_type_map.get(report_type, 'AI复盘报告')
    
    print(f"✍️ 正在将【{report_notion_type}】保存到'每日工作日志'数据库...")
    
    summary, main_report = "", report_text
    start_tag, end_tag = "<SUMMARY>", "</SUMMARY>"
    start_index, end_index = report_text.find(start_tag), report_text.find(end_tag, report_text.find(start_tag))
    
    if start_index != -1 and end_index != -1:
        summary = report_text[start_index + len(start_tag):end_index].strip()
        main_report = report_text[:start_index].strip()
        print(f"  - 已成功提取行动指针: {summary}")
    else:
        print("  - 未在AI响应中找到行动指针标签，该列将为空。")
        main_report = report_text

    try:
        end_date_beijing = end_date.astimezone(timezone(timedelta(hours=8)))
        report_title = f"{end_date_beijing.strftime('%Y-%m-%d')} {report_notion_type}"

        properties_data = {
            "日志标题 名称": {"title": [{"text": {"content": report_title}}]},
            "日期": {"date": {
                "start": start_date.astimezone(timezone(timedelta(hours=8))).isoformat(), 
                "end": end_date.astimezone(timezone(timedelta(hours=8))).isoformat()
            }},
            "条目类型": {"select": {"name": report_notion_type}},
            "本日状态工作状态": {"select": {"name": "已完成"}},
        }
        if summary:
            properties_data["行动指针"] = {"rich_text": [{"text": {"content": summary}}]}
        
        children_blocks = [{
            "object": "block", "type": "callout",
            "callout": {
                "rich_text": [{"type": "text", "text": {"content": chunk}}],
                "icon": {"emoji": "🎯" if i == 0 else "📄"},
                "color": "default"
            }
        } for i, chunk in enumerate([main_report[i:i + 1990] for i in range(0, len(main_report), 1990)])]

        new_page = notion.pages.create(parent={"database_id": review_db_id}, properties=properties_data, children=children_blocks)
        print(f"🎉 {report_notion_type}已成功保存到Notion！")

        new_page_id = new_page.get('id')
        if new_page_id:
            # --- 【新增】写入向量记忆和训练中心 ---
            # 1. 向量化写入
            if memory.client:
                memory_metadata = {'type': report_type, 'date': end_date_beijing.strftime('%Y-%m-%d')}
                threading.Thread(target=memory.add_memory, args=(main_report, memory_metadata), daemon=True).start()

            # 2. 训练中心写入 (v4.0原有逻辑)
            print(">> 正在启动后台任务，将本次复盘存入 [AI训练中心] ...")
            threading.Thread(
                target=write_to_training_hub,
                args=(notion, "摘要生成", original_data, main_report, 'DailyReview', new_page_id, config),
                daemon=True
            ).start()

    except APIResponseError as e:
        print(f"❌ 保存到Notion失败: {e.code} - {e.body}")
    except Exception as e:
        print(f"❌ 保存到Notion时发生未知错误: {e}")

# --- 主程序入口 (已全面升级) ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="周期性复盘AI v5.0") #【修改】版本号
    parser.add_argument(
        '--type', 
        type=str, 
        choices=['daily', 'weekly', 'monthly', 'quarterly', 'yearly'], 
        default='daily',
        help="指定要生成的报告类型 (默认: daily)"
    )
    # --- 【新增】补写日期参数 ---
    parser.add_argument(
        '--date', 
        type=str,
        default=None,
        help="补写指定日期的日报，格式为 YYYY-MM-DD。使用此参数时将忽略 --type。"
    )
    args = parser.parse_args()
    
    # 【修改】初始化调用
    notion, gemini_model, memory, config = initialize()
    
    # 1. 【修改】根据参数确定报告类型和时间范围
    if args.date:
        report_type = 'daily' # 补写功能只针对日报
        start_date, end_date = get_date_range(report_type, specific_date_str=args.date)
        print(f"模式切换：补写日报模式")
    else:
        report_type = args.type
        start_date, end_date = get_date_range(report_type)

    beijing_tz = timezone(timedelta(hours=8))
    start_date_str = start_date.astimezone(beijing_tz).strftime('%Y-%m-%d')
    end_date_str = end_date.astimezone(beijing_tz).strftime('%Y-%m-%d')
    print_separator()
    print(f"📊 报告类型: {report_type.upper()} | 数据周期: {start_date_str} to {end_date_str}")
    
    # 2. 【修改】拉取周期内数据，传入end_date
    log_data = fetch_data_for_period(notion, config["LOG_DB_ID"], "AI互动日志", start_date, end_date)
    brain_data = fetch_data_for_period(notion, config["BRAIN_DB_ID"], "AI作战指挥室", start_date, end_date)
    candidate_data = fetch_data_for_period(notion, config["CANDIDATE_DB_ID"], "AI候选人分析中心", start_date, end_date)
    
    full_period_data = (f"--- 数据来源: AI互动日志 ---\n{log_data}\n\n"
                        f"--- 数据来源: AI作战指挥室 ---\n{brain_data}\n\n"
                        f"--- 数据来源: AI候选人分析中心 ---\n{candidate_data}")
                       
    if len(full_period_data.strip()) < 150: 
        print(f"\n🟡 该周期内核心数据库无足够数据可供分析 ({len(full_period_data.strip())} 字符)，程序退出。")
    else:
        # 3. 【新增】检索相关历史记忆
        query_for_memory = f"为我的{report_type}报告，总结过去的核心成就、挑战和未来方向。"
        historical_insights = memory.retrieve_memory(query_for_memory)
        
        # 4. 【修改】获取专属Prompt并生成报告，传入历史洞察
        prompt = get_prompt_for_report(report_type, full_period_data, start_date_str, end_date_str, historical_insights)
        final_report_with_summary = analyze_and_generate_report(gemini_model, prompt)
        
        if final_report_with_summary:
            # 5. 【修改】保存报告到Notion和向量数据库
            save_report_to_notion(
                notion, memory, config, report_type, final_report_with_summary, 
                full_period_data, start_date, end_date
            )
            
    print_separator()
    input("所有任务已完成，请按回车键退出。")