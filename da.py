# ==============================================================================
#                      周期性复盘AI (Periodic Review AI) v5.5
#                      (Google Search & Vector Memory - 完整兼容版)
# ==============================================================================
# 版本说明 v5.5:
# - 【新增-外部感知】以非侵入式方式集成Google搜索，实现情境感知战略复盘。
#   - 【智能提取】在分析前，先用AI从周期数据中提取最有价值的搜索关键词。
#   - 【自动搜索】自动执行Google搜索，获取与您工作相关的最新资讯、技术文章或竞品动态。
#   - 【深度融合】将搜索到的外部情报注入最终的分析Prompt，让报告更具战略深度。
# - 【原则】严格遵守不删除任何原v5.0代码功能，所有新功能均为新增或在原流程中插入。
# - 【保留】Notion写入分块机制、向量数据库逻辑、补写日报功能等均保持原样。
# - 【依赖更新】需要安装 `google-api-python-client` (`pip install google-api-python-client`)。
# - 【配置更新】需要在 .env 文件中配置 `GOOGLE_API_KEY` 和 `GOOGLE_CSE_ID` (可选)。
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
import chromadb
# 【【【 新增依赖 】】】
import json
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- 原有函数，保持不变 ---
def print_separator():
    print("\n" + "="*70 + "\n")

# --- 原有函数，保持不变 ---
def clean_text(text):
    """文本净化器，移除无效字符，确保API调用成功。"""
    if not isinstance(text, str): return ""
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)

# --- 原有函数，保持不变 ---
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

# --- 原有类，保持不变 ---
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
            
            self.collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[report_text],
                metadatas=[metadata]
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

# --- 【【【 新增：Google搜索模块 】】】 ---
def perform_google_search(query: str, api_key: str, cse_id: str) -> str:
    """执行Google搜索并返回格式化的结果摘要。"""
    try:
        service = build("customsearch", "v1", developerKey=api_key)
        res = service.cse().list(q=query, cx=cse_id, num=3).execute() # 搜索前3个结果
        if 'items' not in res:
            return f"对于查询 '{query}'，没有找到相关结果。"
        snippets = [f"- {item['title']}\n  {item.get('snippet', '无摘要')}" for item in res['items']]
        return f"--- 关于 '{query}' 的搜索结果 ---\n" + "\n".join(snippets)
    except HttpError as e:
        return f"Google搜索API错误: {e.reason}"
    except Exception as e:
        return f"执行Google搜索时发生未知错误: {e}"

def extract_search_queries_from_data(gemini_model, data_text):
    """使用AI从原始数据中提取出最有价值的Google搜索关键词。"""
    print("  - 🤖 正在分析周期数据，提取最有价值的搜索关键词...")
    try:
        prompt = f"""
        # 任务
        分析以下工作日志，识别出2-3个最具有研究价值的核心主题、技术、公司名或遇到的问题。
        这些关键词应该能通过Google搜索，为即将生成的复盘报告带来最大的外部视角和价值。

        # 规则
        - 只关注那些通过外部信息能得到增强的主题。
        - 忽略日常琐事。
        - 以JSON列表的形式返回，例如：["AI Agent最新进展", "竞品公司X动态", "Python uvloop性能优化"]

        # 工作日志
        {data_text[:4000]}
        """
        response = gemini_model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        queries = json.loads(response.text)
        if isinstance(queries, list) and queries:
            print(f"  - ✅ 成功提取到关键词: {queries}")
            return queries
        return []
    except Exception as e:
        print(f"  - ❌ 提取搜索关键词失败: {e}")
        return []

# --- 1. 初始化与配置加载 (已修改，增加Google搜索相关逻辑) ---
def initialize():
    """加载配置并初始化所有服务"""
    print_separator()
    print("🚀 启动周期性复盘AI引擎 (v5.5 - 完整兼容版)...")
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
        "CHROMA_DB_PATH": os.getenv("CHROMA_DB_PATH"),
        "CHROMA_COLLECTION_NAME": os.getenv("CHROMA_COLLECTION_NAME"),
        # 【【【 新增配置项读取 】】】
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
        "GOOGLE_CSE_ID": os.getenv("GOOGLE_CSE_ID"),
    }
    if not all([config["NOTION_TOKEN"], config["API_KEY"], config["REVIEW_DB_ID"]]):
        print("❌ 错误：关键配置缺失！(NOTION_API_KEY, GEMINI_API_KEY, DAILY_REVIEW_DATABASE_ID 必须在 .env 文件中配置)")
        sys.exit(1)
    
    # 【【【 新增配置检查 】】】
    config["ENABLE_GOOGLE_SEARCH"] = bool(config["GOOGLE_API_KEY"] and config["GOOGLE_CSE_ID"])
    if not config["ENABLE_GOOGLE_SEARCH"]:
        print("🟡 [警告] Google搜索未配置 (GOOGLE_API_KEY, GOOGLE_CSE_ID)，外部情报模块将禁用。")

    try:
        notion = Client(auth=config["NOTION_TOKEN"])
        genai.configure(api_key=config["API_KEY"])
        # 【【【 修改：使用两个模型，一个用于快速任务，一个用于深度分析 】】】
        gemini_flash_model = genai.GenerativeModel('models/gemini-2.5-flash')
        gemini_pro_model = genai.GenerativeModel('models/gemini-2.5-pro') # 保持原有的Pro模型
        memory = VectorMemory(config["CHROMA_DB_PATH"], config["CHROMA_COLLECTION_NAME"])
        print("✅ Notion, Gemini (Flash & Pro) 和 向量记忆模块 初始化成功！")
        # 【【【 修改：返回更多模型和完整的config 】】】
        return notion, gemini_flash_model, gemini_pro_model, memory, config
    except Exception as e:
        print(f"❌ 初始化失败: {e}"); sys.exit(1)

# --- 原有函数，保持不变 ---
def get_date_range(report_type, specific_date_str=None):
    if specific_date_str:
        try:
            beijing_tz = timezone(timedelta(hours=8))
            target_date = datetime.strptime(specific_date_str, '%Y-%m-%d')
            start_date_local = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=beijing_tz)
            end_date_local = target_date.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=beijing_tz)
            return start_date_local.astimezone(timezone.utc), end_date_local.astimezone(timezone.utc)
        except ValueError:
            print(f"❌ 日期格式错误: '{specific_date_str}'。请使用 YYYY-MM-DD 格式。程序退出。")
            sys.exit(1)
    end_date = datetime.now(timezone.utc)
    today_beijing = datetime.now(timezone(timedelta(hours=8))).date()
    start_of_day_beijing = datetime.combine(today_beijing, datetime.min.time(), tzinfo=timezone(timedelta(hours=8)))
    if report_type == 'daily':
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
        start_date = start_of_day_beijing.astimezone(timezone.utc)
    return start_date, end_date

# --- 原有函数，保持不变 ---
def fetch_data_for_period(notion, db_id, db_name, start_date, end_date):
    if not db_id:
        print(f"🟡 跳过 [{db_name}]：未在.env中配置其数据库ID。"); return ""
    print(f"⏳ 正在从 [{db_name}] 数据库拉取周期内数据...")
    try:
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

# --- AI Prompt生成器 (已修改，增加Google搜索结果注入) ---
def get_prompt_for_report(report_type, data_text, start_date_str, end_date_str, historical_insights="", google_search_summary=""):
    """根据报告类型生成专属的AI Prompt, 并注入历史洞察和Google搜索结果"""
    # --- 原有逻辑 ---
    report_titles = {'daily': '每日战略复盘与未来规划', 'weekly': '每周战略回顾与展望', 'monthly': '月度战略复盘与目标校准', 'quarterly': '季度深度复盘与战略调整', 'yearly': '年度综合复盘与未来战略规划'}
    report_title = report_titles.get(report_type, '周期性复盘报告')
    period_scopes = {'daily': ('今日', '明日'), 'weekly': ('本周', '下周'), 'monthly': ('本月', '下月'), 'quarterly': ('本季度', '下季度'), 'yearly': ('本年度', '下年度')}
    scope_texts = {'daily': ("今日核心成果概览", "明日核心优先事项"), 'weekly': ("本周核心成果与趋势", "下周核心目标与策略"), 'monthly': ("本月关键进展与挑战", "下月战略重点"), 'quarterly': ("本季度重大成就与瓶颈", "下季度核心战略方向"), 'yearly': ("本年度核心里程碑与教训", "下一年度战略蓝图")}
    current_scope, next_scope = scope_texts[report_type]
    
    # --- 【【【 修改：将原有的历史洞察部分和新增的外部情报部分合并，增强结构 】】】 ---
    external_context_section = f"""# 实时外部情报 (来自Google搜索)
{google_search_summary if google_search_summary else "本次未进行外部情报搜索。"}
---
""" if google_search_summary else ""
    
    historical_context_section = f"""# 相关历史洞察 (从我的记忆库中检索)
{historical_insights if historical_insights else "未检索到相关历史记忆。"}
---
"""
    # --- 【【【 修改：更新Prompt模板，使其结构更清晰，并包含新模块 】】】 ---
    prompt = f"""
# 角色与任务
你是一位顶级的、具备“内部记忆”和“外部感知”能力的战略顾问。你的任务是结合【实时外部情报】(如果提供)、【相关历史洞察】(如果提供)和我提供的【当前周期数据】，生成一份极具深度和前瞻性的复盘报告。

{external_context_section}
{historical_context_section}

# 当前待分析数据
---
【{period_scopes[report_type][0] if isinstance(period_scopes[report_type], tuple) else period_scopes[report_type]}工作数据汇总 (从 {start_date_str} 到 {end_date_str})】
{data_text}
---

# 输出指令与格式
你必须严格按照以下Markdown格式输出。在分析时，请特别注意将【外部情报】和【历史洞察】与【当前数据】进行交叉引用和深度思考。

### 第1部分：报告主体
---
## {report_title} - {end_date_str}
### 1. {current_scope} (Executive Summary)
*   **[用2-4个要点，高度概括本周期内的核心产出、关键趋势和活动]**
### 2. 亮点与高光时刻 (Key Achievements & Highlights)
*   **[识别并阐述1-3件最有价值的事，并结合外部信息分析其对于 {period_scopes[report_type][0] if isinstance(period_scopes[report_type], tuple) else period_scopes[report_type]} 目标的战略意义]**
### 3. 瓶颈与战略反思 (Bottlenecks & Strategic Reflections)
*   **[分析本周期内遇到的主要障碍、效率瓶颈，并进行更深层次的战略原因反思。是资源问题？方向问题？还是执行问题？]**
### 4. 跨周期洞察与模式识别 (Cross-Period Insights & Pattern Recognition)
*   **浮现的主题:** [本周期内反复出现的新主题或新机会是什么？外部世界是否也在讨论这个主题？]
*   **模式与关联:** [不同工作任务之间是否存在可以利用的潜在关联或模式？历史洞察是否揭示了重复出现的模式？]
*   **战略假设验证:** [本周期的实践，是验证了还是挑战了我们之前的战略假设？外部情报是否提供了新的视角？]
### 5. {next_scope} ({'Priorities for Next Period' if report_type != 'daily' else 'Top Priorities for Tomorrow'})
- [ ] **[基于以上所有分析，特别是外部情报的启发，生成2-4个最具战略价值的待办事项或目标，用于指导下一周期]**
- [ ] **[第二个待办事项]**
---

### 第2部分：行动指针
在报告主体之后，你必须另起一行，提供一个被 `<SUMMARY>` 和 `</SUMMARY>` 标签包裹的、不超过两句话的行动指针。这个指针要高度浓缩报告中最核心的、最需要我关注的行动建议，作为下一周期的最高指导原则。
【示例】: `<SUMMARY>下周应集中精力将AI候选人分析流程标准化，并启动对'项目X'的初步技术预研，以验证其长期价值。</SUMMARY>`
"""
    return prompt

# --- 原有函数，保持不变 ---
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

# --- 原有函数，保持不变，特别是children_blocks的分块逻辑 ---
def save_report_to_notion(notion, memory, config, report_type, report_text, original_data, start_date, end_date):
    """将报告保存到Notion，并触发向量化和训练中心写入。"""
    review_db_id = config["REVIEW_DB_ID"]
    report_type_map = { 'daily': 'AI复盘报告', 'weekly': 'AI周报', 'monthly': 'AI月报', 'quarterly': 'AI季报', 'yearly': 'AI年报' }
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
            "日期": {"date": {"start": start_date.astimezone(timezone(timedelta(hours=8))).isoformat(), "end": end_date.astimezone(timezone(timedelta(hours=8))).isoformat()}},
            "条目类型": {"select": {"name": report_notion_type}},
            "本日状态工作状态": {"select": {"name": "已完成"}},
        }
        if summary:
            properties_data["行动指针"] = {"rich_text": [{"text": {"content": summary}}]}
        
        # --- 【【【 您成熟好用的分块逻辑，原封不动 】】】 ---
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
            if memory.client:
                memory_metadata = {'type': report_type, 'date': end_date_beijing.strftime('%Y-%m-%d')}
                threading.Thread(target=memory.add_memory, args=(main_report, memory_metadata), daemon=True).start()
            print(">> 正在启动后台任务，将本次复盘存入 [AI训练中心] ...")
            threading.Thread(target=write_to_training_hub,args=(notion, "摘要生成", original_data, main_report, 'DailyReview', new_page_id, config),daemon=True).start()
    except APIResponseError as e:
        print(f"❌ 保存到Notion失败: {e.code} - {e.body}")
    except Exception as e:
        print(f"❌ 保存到Notion时发生未知错误: {e}")

# --- 主程序入口 (已修改，插入了Google搜索流程) ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="周期性复盘AI v5.5 - 完整兼容版")
    parser.add_argument('--type', type=str, choices=['daily', 'weekly', 'monthly', 'quarterly', 'yearly'], default='daily', help="指定要生成的报告类型 (默认: daily)")
    parser.add_argument('--date', type=str, default=None, help="补写指定日期的日报，格式为 YYYY-MM-DD。")
    args = parser.parse_args()
    
    # 【修改】初始化调用会返回更多模型
    notion, gemini_flash_model, gemini_pro_model, memory, config = initialize()
    
    # 1. 确定报告类型和时间范围 (原有逻辑)
    if args.date:
        report_type = 'daily'
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
    
    # 2. 拉取周期内数据 (原有逻辑)
    log_data = fetch_data_for_period(notion, config["LOG_DB_ID"], "AI互动日志", start_date, end_date)
    brain_data = fetch_data_for_period(notion, config["BRAIN_DB_ID"], "AI作战指挥室", start_date, end_date)
    candidate_data = fetch_data_for_period(notion, config["CANDIDATE_DB_ID"], "AI候选人分析中心", start_date, end_date)
    full_period_data = (f"--- 数据来源: AI互动日志 ---\n{log_data}\n\n"
                        f"--- 数据来源: AI作战指挥室 ---\n{brain_data}\n\n"
                        f"--- 数据来源: AI候选人分析中心 ---\n{candidate_data}")
                       
    if len(full_period_data.strip()) < 150: 
        print(f"\n🟡 该周期内核心数据库无足够数据可供分析 ({len(full_period_data.strip())} 字符)，程序退出。")
    else:
        # --- 【【【 新增的Google搜索流程 】】】 ---
        google_search_summary = ""
        if config["ENABLE_GOOGLE_SEARCH"]:
            print_separator()
            print("🌐 正在启动外部情报搜集模块...")
            # 使用Flash模型提取关键词
            queries = extract_search_queries_from_data(gemini_flash_model, full_period_data)
            if queries:
                search_results = [perform_google_search(q, config["GOOGLE_API_KEY"], config["GOOGLE_CSE_ID"]) for q in queries]
                google_search_summary = "\n\n".join(search_results)
            else:
                print("  - 未能提取到有价值的搜索关键词，跳过外部情报搜集。")
        
        # 3. 检索相关历史记忆 (原有逻辑)
        print_separator()
        query_for_memory = f"为我的{report_type}报告，总结过去的核心成就、挑战和未来方向。"
        historical_insights = memory.retrieve_memory(query_for_memory)
        
        # 4. 获取专属Prompt并生成报告 (修改：注入google_search_summary)
        print_separator()
        prompt = get_prompt_for_report(report_type, full_period_data, start_date_str, end_date_str, historical_insights, google_search_summary)
        
        # 5. 调用AI进行分析 (修改：使用更强大的Pro模型)
        final_report_with_summary = analyze_and_generate_report(gemini_pro_model, prompt)
        
        # 6. 保存报告到Notion (原有逻辑)
        if final_report_with_summary:
            save_report_to_notion(
                notion, memory, config, report_type, final_report_with_summary, 
                full_period_data, start_date, end_date
            )
            
    print_separator()
    input("所有任务已完成，请按回车键退出。")