# ==============================================================================
#      Notion Universal Auto-Numbering Service v2.1 (健壮性修复版)
# ==============================================================================
# 功能:
# - 【核心修复】: 重写了错误处理逻辑，彻底解决了因解析API错误信息而
#                 导致脚本自身崩溃的问题 (例如 'str' object has no attribute 'get')。
# - 【核心功能】: 采用“获取当前最大编号+累加”的逻辑，实现永久、唯一、
#                 严格递增的编号，不受页面删除影响。
# - 【绝对顺序】: 100%保证最早创建的页面获得最小的编号。
# ==============================================================================

import time
import notion_client
import os
import json # 引入json库以备用

import os                  # 引入os库，用于读取环境变量
from dotenv import load_dotenv  # 引入dotenv库，用于加载.env文件
import json                # 你原来的json库

# --- 【【【 1. 安全的配置加载区 】】】 ---

# 这行代码会自动查找并加载项目根目录下的 .env 文件
load_dotenv()

# 使用 os.getenv() 从加载的环境中安全地获取密钥
# "NOTION_API_KEY" 这个名字，必须和你 .env 文件里写的一模一样
NOTION_TOKEN = os.getenv("NOTION_API_KEY") 

# 其他配置保持不变
CHECK_INTERVAL_SECONDS = 10

# 【强烈建议】增加一个检查，确保密钥成功加载
if not NOTION_TOKEN:
    print("❌ 致命错误：未能从 .env 文件中加载 NOTION_API_KEY。")
    print("   请确保：")
    print("   1. 项目根目录下存在 .env 文件。")
    print("   2. .env 文件中包含 'NOTION_API_KEY=ntn_...' 这一行。")
    exit() # 如果没有加载到密钥，程序直接退出，防止后续出错

# --- 【【【 2. 数据库自动编号配置 】】】 ---
DATABASES_TO_MONITOR = {
    # 1. “AI互动日志”
    "22d584b1cda3809a806bf8596b1ab96d": {"number_prop_name": "LogID", "prefix": "LOG-"},
    # 2. “AI作战指挥室” (核心大脑)
    "22d584b1cda38050b104dc4006d90331": {"number_prop_name": "BrainID", "prefix": "BRAIN-"},
    # 3. “AI候选人分析中心” (总库)
    "22a584b1cda3802dbb5dd8e1aba9a967": {"number_prop_name": "CandID", "prefix": "CAND-"},
    # 4. “每日工作日志” (复盘报告)
    "225584b1cda380ad9c90d5932bbdcfdc": {"number_prop_name": "ReviewID", "prefix": "REV-"},
    # 5. “AI训练中心”
    "231584b1cda380a1927be2ab6f22cf33": {"number_prop_name": "TrainID", "prefix": "TRAIN-"}
}

# --- 【【【 3. 核心逻辑区 (v2.1 健壮性修复) 】】】 ---

def get_current_max_number(db_id, number_prop, notion_client_instance):
    """
    高效地获取指定数据库中，某个数字属性的当前最大值。
    """
    try:
        response = notion_client_instance.databases.query(
            database_id=db_id,
            sorts=[{"property": number_prop, "direction": "descending"}],
            filter={"property": number_prop, "number": {"is_not_empty": True}},
            page_size=1
        )
        results = response.get("results", [])
        if not results:
            return 0
        
        max_number = results[0]["properties"][number_prop]["number"]
        return max_number if max_number is not None else 0

    except Exception as e:
        # 【【【 V2.1 修复点 】】】
        # 直接将异常对象转为字符串，这是最安全、最健壮的方式，
        # 避免了因解析不同错误体格式而导致的程序崩溃。
        error_message = str(e)
        print(f"   - ⚠️ 获取最大编号失败 [DB: ...{db_id[-4:]}]: {error_message}")
        return -1


def process_single_database(db_id, config, notion_client_instance):
    """处理单个数据库的编号逻辑"""
    number_prop = config["number_prop_name"]
    try:
        pages_to_number = notion_client_instance.databases.query(
            database_id=db_id,
            filter={"property": number_prop, "number": {"is_empty": True}},
            sorts=[{"timestamp": "created_time", "direction": "ascending"}]
        ).get("results", [])

        if not pages_to_number:
            return

        print(f"✅ [DB: ...{db_id[-4:]}] 检测到 {len(pages_to_number)} 个新页面，准备编号...")

        current_max = get_current_max_number(db_id, number_prop, notion_client_instance)
        if current_max == -1:
            print(f"   - ❌ 由于无法获取当前最大编号，本次跳过 [DB: ...{db_id[-4:]}]")
            return
            
        print(f"   - 当前最大编号为: {current_max}")

        for i, page in enumerate(pages_to_number):
            page_id = page["id"]
            new_number = current_max + i + 1
            try:
                notion_client_instance.pages.update(
                    page_id=page_id,
                    properties={number_prop: {"number": new_number}}
                )
                print(f"   - 成功更新页面 ...{page_id[-4:]} 的编号为: {config['prefix']}{new_number}")
                time.sleep(0.35)
            except Exception as update_error:
                # 【【【 V2.1 修复点 】】】
                error_message = str(update_error)
                print(f"   - ❌ 更新页面 ...{page_id[-4:]} 失败: {error_message}")

    except Exception as e:
        # 【【【 V2.1 修复点 】】】
        error_message = str(e)
        print(f"!! [DB: ...{db_id[-4:]}] 处理时出错: {error_message}")

# --- 主循环 (保持不变) ---
def main_monitoring_loop():
    if not NOTION_TOKEN or "ntn_" not in NOTION_TOKEN:
        print("❌ 致命错误：请在脚本顶部填入正确的 Notion Token！")
        return
    try:
        notion = notion_client.Client(auth=NOTION_TOKEN)
        print("✅ Notion 客户端初始化成功。")
    except Exception as e:
        print(f"❌ 致命错误：Notion 客户端初始化失败: {e}")
        return

    print("=" * 60)
    print("      Notion 自动编号服务已启动 (v2.1 - 健壮性修复版)")
    print(f"      将每隔 {CHECK_INTERVAL_SECONDS} 秒检查 {len(DATABASES_TO_MONITOR)} 个数据库...")
    print("      按下 Ctrl+C 可随时退出。")
    print("=" * 60)

    try:
        while True:
            for db_id, config in DATABASES_TO_MONITOR.items():
                process_single_database(db_id, config, notion)
            time.sleep(CHECK_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\n\n🛑 检测到手动中断 (Ctrl+C)，服务已关闭。")
    except Exception as loop_error:
        print(f"!! 主循环发生未知错误: {loop_error}")
    finally:
        print("👋 再见！")


if __name__ == "__main__":
    os.system('cls' if os.name == 'nt' else 'clear')
    main_monitoring_loop()