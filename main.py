# ==============================================================================
#           AI实时字幕工具 v5.0 (终极诊断版)
# ==============================================================================
import os
import sys
import threading
import time
import numpy as np
import pyaudio
from dotenv import load_dotenv
import tkinter as tk
from datetime import datetime, timezone, timedelta

# --- 库导入与检查 ---
try:
    import whisper
    import google.generativeai as genai
    from notion_client import Client, APIResponseError
    import resampy
except ImportError:
    print("错误：核心库未安装！\n请在激活的虚拟环境中运行以下命令:\npip install openai-whisper google-generativeai notion-client resampy tk")
    sys.exit()

# --- 配置加载 (指向AI日志库) ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
NOTION_API_KEY = os.getenv("NOTION_API_KEY") 
TOOLBOX_LOG_DATABASE_ID = os.getenv("TOOLBOX_LOG_DATABASE_ID")

# --- 【【【 诊断步骤 1：检查配置是否正确加载 】】】 ---
print("\n--- 启动诊断信息 ---")
print(f"DEBUG: GEMINI_API_KEY Loaded: {'Yes' if GEMINI_API_KEY and len(GEMINI_API_KEY) > 10 else 'No or Invalid'}")
print(f"DEBUG: NOTION_API_KEY Loaded: {'...'+NOTION_API_KEY[-4:] if NOTION_API_KEY and len(NOTION_API_KEY) > 10 else 'No or Invalid'}")
print(f"DEBUG: TOOLBOX_LOG_DATABASE_ID Loaded: {TOOLBOX_LOG_DATABASE_ID if TOOLBOX_LOG_DATABASE_ID else 'None'}")
print("---------------------\n")


# --- 全局常量 ---
DEVICE_INDEX = 2
RECORD_SECONDS = 8
TARGET_RATE = 16000

# --- 全局状态变量 ---
root = None 
subtitle_text = None 
worker_thread_stop_event = threading.Event()

# ==============================================================================
#  核心工作逻辑
# ==============================================================================
def audio_processing_loop():
    global subtitle_text
    
    print("工作线程启动，正在初始化模型...")
    notion_client = None
    try:
        whisper_model = whisper.load_model('base.en')
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model = genai.GenerativeModel('models/gemini-2.5-flash')
        if NOTION_API_KEY and len(NOTION_API_KEY) > 10:
             notion_client = Client(auth=NOTION_API_KEY)
             print("DEBUG: Notion Client 初始化成功。")
        else:
             print("DEBUG: Notion Client 初始化失败，因为NOTION_API_KEY无效。")
        print("模型初始化完毕。")
    except Exception as e:
        if root: subtitle_text.set(f"模型初始化失败: {e}")
        print(f"模型初始化失败: {e}")
        worker_thread_stop_event.set()
        return

    p = pyaudio.PyAudio()
    try:
        device_info = p.get_device_info_by_index(DEVICE_INDEX)
    except OSError:
        error_msg = f"错误：找不到设备索引 {DEVICE_INDEX}。\n请检查您的音频设备连接。"
        if root: subtitle_text.set(error_msg)
        print(error_msg)
        worker_thread_stop_event.set()
        p.terminate()
        return
        
    NATIVE_RATE = int(device_info['defaultSampleRate'])
    NATIVE_CHANNELS = 1 if device_info['maxInputChannels'] >= 1 else device_info['maxInputChannels']
    
    stream = p.open(format=pyaudio.paInt16, channels=NATIVE_CHANNELS, rate=NATIVE_RATE,
                    input=True, input_device_index=DEVICE_INDEX, frames_per_buffer=1024)
    print(f"音频流已开启 (设备 {DEVICE_INDEX})。字幕功能正常运行。")

    while not worker_thread_stop_event.is_set():
        try:
            frames = stream.read(NATIVE_RATE * RECORD_SECONDS, exception_on_overflow=False)
            audio_data = np.frombuffer(frames, dtype=np.int16)

            if NATIVE_CHANNELS > 1: audio_data = audio_data.reshape(-1, NATIVE_CHANNELS)[:, 0]
            if NATIVE_RATE != TARGET_RATE: audio_data = resampy.resample(audio_data.astype(float), NATIVE_RATE, TARGET_RATE)

            audio_normalized = audio_data.astype(np.float32) / 32768.0
            result = whisper_model.transcribe(audio_normalized, fp16=False)
            english_text = result['text'].strip()

            if english_text:
                response = gemini_model.generate_content(f"Translate to Simplified Chinese, returning only the translation:\n{english_text}")
                chinese_text = response.text.strip()
                
                new_text = f"{english_text}\n{chinese_text}"
                if subtitle_text: subtitle_text.set(new_text)
                print(f"新字幕: {new_text.replace(chr(10), ' / ')}")
                
                # --- 【【【 诊断步骤 2：检查调用条件 】】】 ---
                if notion_client and TOOLBOX_LOG_DATABASE_ID:
                    print("DEBUG: 条件满足，准备启动Notion上传线程...")
                    threading.Thread(target=save_log_to_notion, args=(notion_client, "实时字幕", english_text, chinese_text)).start()
                else:
                    print("DEBUG: 未启动Notion上传，因为 notion_client 或 TOOLBOX_LOG_DATABASE_ID 无效。")

        except Exception as e:
            error_msg_loop = f"音频处理循环出错: {e}"
            if subtitle_text: subtitle_text.set(error_msg_loop)
            print(error_msg_loop)
            time.sleep(1)

    stream.stop_stream(); stream.close(); p.terminate()
    print("工作线程已停止。")

def save_log_to_notion(client, log_type: str, input_text: str, output_text: str):
    # --- 【【【 诊断步骤 3：捕获并打印详细的Notion错误 】】】 ---
    try:
        page_title = f"【{log_type}】{input_text[:80]}"
        print("--- (联动日志) 正在尝试上传到Notion... ---")
        current_date_iso = datetime.now(timezone(timedelta(hours=8))).isoformat()
        properties_data = {
            "主题": {"title": [{"text": {"content": page_title}}]}, 
            "类型": {"select": {"name": log_type}},
            "输入内容": {"rich_text": [{"text": {"content": input_text}}]}, 
            "输出摘要": {"rich_text": [{"text": {"content": output_text}}]},
            "记录日期": {"date": {"start": current_date_iso}}
        }
        client.pages.create(parent={"database_id": TOOLBOX_LOG_DATABASE_ID}, properties=properties_data)
        print("--- (联动日志) 上传成功！ ---")
    except APIResponseError as error:
        # 专门捕获Notion的API错误
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!!  诊断错误：Notion API返回了错误！")
        print(f"!!!  错误代码 (Code): {error.code}")
        print(f"!!!  错误信息 (Message): {error.message}")
        print("!!!  请重点检查：")
        print("!!!  1. 你的 'TOOLBOX_LOG_DATABASE_ID' 是否正确？")
        print("!!!  2. 你的机器人是否已经连接到了这个数据库？(在数据库页面右上角...菜单里点'Add connections')")
        print("!!!  3. 数据库里的列名是否和代码里的'主题', '类型', '输入内容'等完全一致？")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    except Exception as e:
        # 捕获其他所有可能的错误
        print(f"--- (联动日志) 保存到Notion时发生未知错误，详细信息: {e!r} ---")


def on_closing():
    print("窗口关闭信号已收到，正在停止后台线程...")
    worker_thread_stop_event.set()
    time.sleep(0.5)
    if root:
        root.destroy()
    print("程序已退出。")

# ==============================================================================
#  主程序入口
# ==============================================================================
if __name__ == '__main__':
    root = tk.Tk()
    subtitle_text = tk.StringVar()
    subtitle_text.set("正在初始化模型，请稍候...")

    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    
    window_width = 900
    window_height = 120 
    x_pos = (screen_width - window_width) // 2
    y_pos = screen_height - window_height - 50 
    
    root.geometry(f'{window_width}x{window_height}+{x_pos}+{y_pos}')
    
    root.overrideredirect(True) 
    root.wm_attributes("-topmost", True)
    root.config(bg='#121212') 
    
    label = tk.Label(root, textvariable=subtitle_text, font=("Arial", 18, "bold"), fg="white", bg=root.cget('bg'), wraplength=window_width-20, justify="left")
    label.pack(expand=True, fill='both', pady=10, padx=10)
    
    worker_thread = threading.Thread(target=audio_processing_loop)
    worker_thread.daemon = True
    worker_thread.start()

    print("GUI已就绪，后台线程已启动。字幕窗口将直接显示。")
    print("要退出程序，请直接关闭这个黑色的命令行窗口。")
    
    root.mainloop()