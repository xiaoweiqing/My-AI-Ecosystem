# ==============================================================================
#           AI智能助手 v13.0 (终极赎罪版 - 显示修复)
# ==============================================================================
# 版本说明:
# - 【郑重承诺】: 本版本为最终显示修复版，旨在彻底解决字幕显示不全、中英文错乱的致命BUG。
# - 【终极UI重构】: 废除单一标签，采用【上下双标签】布局，为中英文提供独立显示空间，确保永不挤压。
# - 【字体优化】: 采纳您的建议，将字体调整为更清晰的16号，优化视觉体验。
# - 【功能冻结】: 100%保留v11.0版本已恢复的所有稳定后台功能，不再做任何修改。
# ==============================================================================
import os
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from dotenv import load_dotenv

# --- 模块延迟导入 ---
pyaudio = whisper = genai = Client = resampy = np = None
APIResponseError = None
datetime = timezone = timedelta = re = None

# --- 1. 配置加载 ---
load_dotenv()
try:
    MEETING_MODE_MIC_INDEX = int(os.getenv("MEETING_MODE_MIC_INDEX", "2"))
    SUBTITLE_MODE_DEVICE_INDEX = int(os.getenv("SUBTITLE_MODE_DEVICE_INDEX", "2"))
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    NOTION_API_KEY = os.getenv("NOTION_API_KEY")
    TOOLBOX_LOG_DATABASE_ID = os.getenv("TOOLBOX_LOG_DATABASE_ID")
    TRAINING_HUB_DATABASE_ID = os.getenv("TRAINING_HUB_DATABASE_ID")
    MEETING_LOG_DATABASE_ID = os.getenv("MEETING_LOG_DATABASE_ID")
    DAILY_REVIEW_DATABASE_ID = os.getenv("DAILY_REVIEW_DATABASE_ID")
except (TypeError, ValueError):
    err_root = tk.Tk(); err_root.withdraw()
    messagebox.showerror("配置错误", "!! 致命错误 !!\n\n请在 .env 文件中的设备索引是否为数字！")
    sys.exit()

# --- 2. 全局状态变量 ---
root = None; worker_thread = None
# 【v13.0 UI改动】现在需要两个独立的文本变量
english_text_var = None
chinese_text_var = None
worker_thread_stop_event = threading.Event()
is_meeting_running = False

# --- 3. 核心功能函数 (所有后台逻辑均与v11.0保持一致) ---

def open_resilient_stream(pyaudio_instance, device_index):
    standard_sample_rates = [48000, 44100, 16000]
    for rate in standard_sample_rates:
        try:
            stream = pyaudio_instance.open(format=pyaudio.paInt16, channels=1, rate=rate, input=True, input_device_index=device_index, frames_per_buffer=1024)
            print(f"[日志] 音频流以 {rate}Hz 采样率成功开启。")
            return stream, rate
        except: continue
    return None, None

def save_log_and_training_realtime(client, log_type, input_text, output_text):
    if not client or not TOOLBOX_LOG_DATABASE_ID: return
    try:
        page_title = f"【{log_type}】{input_text[:80]}"
        log_props = {"主题": {"title": [{"text": {"content": page_title}}]},"类型": {"select": {"name": log_type}},"输入内容": {"rich_text": [{"text": {"content": input_text}}]},"输出摘要": {"rich_text": [{"text": {"content": output_text}}]}}
        log_page = client.pages.create(parent={"database_id": TOOLBOX_LOG_DATABASE_ID}, properties=log_props)
        log_page_id = log_page.get("id")
        print(f"[实时上传] 1条“{log_type}”记录已上传。")
        if log_page_id and TRAINING_HUB_DATABASE_ID:
            train_props = {"训练任务": {"title": [{"text": {"content": f"【翻译】{input_text[:60]}..."}}]},"任务类型": {"select": {"name": "翻译"}},"源数据 (Input)": {"rich_text": [{"text": {"content": input_text}}]},"理想输出 (Output)": {"rich_text": [{"text": {"content": output_text}}]},"源链接-互动日志": {"relation": [{"id": log_page_id}]}}
            client.pages.create(parent={"database_id": TRAINING_HUB_DATABASE_ID}, properties=train_props)
            print("[实时上传] 1条训练数据已上传。")
    except Exception as e: print(f"[错误] 实时上传失败: {e}")

def batch_upload_to_training_hub(client, training_pairs):
    if not client or not TRAINING_HUB_DATABASE_ID or not training_pairs: return
    print(f"[归档流程] 步骤 5/5: 开始批量上传 {len(training_pairs)} 条对话到训练中心...")
    success_count = 0
    for pair in training_pairs:
        try:
            train_props = {"训练任务": {"title": [{"text": {"content": f"【会议翻译】{pair['en'][:60]}..."}}]},"任务类型": {"select": {"name": "翻译"}},"源数据 (Input)": {"rich_text": [{"text": {"content": pair['en']}}]},"理想输出 (Output)": {"rich_text": [{"text": {"content": pair['cn']}}]}}
            client.pages.create(parent={"database_id": TRAINING_HUB_DATABASE_ID}, properties=train_props)
            success_count += 1
        except Exception as e: print(f"[错误] 批量上传训练数据时失败一条: {e}")
    print(f"[归档流程] 步骤 5/5: 完成！共成功上传 {success_count} / {len(training_pairs)} 条。")

def upload_meeting_and_link_all(client, start_time, log_content, summary, training_data):
    if not client: return
    meeting_page_id, meeting_page_url = None, None
    print("[归档流程] 步骤 2/5: 开始上传至“AI会议纪要库”...")
    if MEETING_LOG_DATABASE_ID:
        try:
            page_title = f"AI会议纪要 - {start_time.strftime('%Y-%m-%d %H:%M')}"
            content_chunks = [log_content[i:i+2000] for i in range(0, len(log_content), 2000)]; content_blocks = [{"type": "paragraph", "paragraph": {"rich_text": [{"text": {"content": chunk}}]}} for chunk in content_chunks if chunk]
            properties = {"会议主题": {"title": [{"text": {"content": page_title}}]}, "会议日期": {"date": {"start": start_time.isoformat()}}, "AI分析摘要": {"rich_text": [{"text": {"content": summary[:2000]}}]}}
            meeting_page = client.pages.create(parent={"database_id": MEETING_LOG_DATABASE_ID}, properties=properties, children=content_blocks[:100])
            meeting_page_id, meeting_page_url = meeting_page.get("id"), meeting_page.get("url")
            print("[归档流程] 步骤 2/5: 成功！")
        except Exception as e: print(f"[错误] 上传至会议库失败: {e}"); return
    print("[归档流程] 步骤 3/5: 开始在“互动日志”中创建归档记录...")
    if TOOLBOX_LOG_DATABASE_ID and meeting_page_url:
        try:
            log_props = {"主题": {"title": [{"text": {"content": f"【会议纪要归档】{page_title}"}}]}, "类型": {"select": {"name": "会议纪要"}}, "输出摘要": {"rich_text": [{"text": {"content": f"AI摘要已生成。\n[点击查看完整纪要]({meeting_page_url})"}}]}}
            client.pages.create(parent={"database_id": TOOLBOX_LOG_DATABASE_ID}, properties=log_props)
            print("[归档流程] 步骤 3/5: 成功！")
        except Exception as e: print(f"[错误] 创建归档日志失败: {e}")
    print("[归档流程] 步骤 4/5: 开始关联到“每日工作日志”...")
    if DAILY_REVIEW_DATABASE_ID and meeting_page_id:
        try:
            date_str = start_time.strftime("%Y-%m-%d")
            query_res = client.databases.query(database_id=DAILY_REVIEW_DATABASE_ID, filter={"property": "日期", "date": {"equals": date_str}})
            daily_log_id = query_res["results"][0]["id"] if query_res["results"] else client.pages.create(parent={"database_id": DAILY_REVIEW_DATABASE_ID}, properties={"日志标题名称": {"title": [{"text": {"content": f"{date_str} AI战略复盘报告"}}]}, "日期": {"date": {"start": date_str}}})['id']
            client.pages.update(page_id=daily_log_id, properties={"关联会议纪要": {"relation": [{"id": meeting_page_id}]}})
            print("[归档流程] 步骤 4/5: 成功！")
        except Exception as e: print(f"[错误] 关联每日日志失败: {e}")
    batch_upload_to_training_hub(client, training_data)

def background_worker(device_index, is_meeting_mode):
    global pyaudio, whisper, genai, Client, resampy, np, APIResponseError, english_text_var, chinese_text_var, datetime, timezone, timedelta, re
    print("\n[日志] 开始动态导入核心库..."); english_text_var.set("正在加载核心库..."); chinese_text_var.set("")
    try:
        import pyaudio; import whisper; import google.generativeai as genai; from notion_client import Client, APIResponseError; import resampy; import numpy as np; from datetime import datetime, timezone, timedelta; import re
    except ImportError as e: error_msg = f"核心库导入失败: {e}\n请确保已安装所有依赖。"; print(f"[错误] {error_msg}"); english_text_var.set(error_msg); return

    print("[日志] 开始初始化AI模型和Notion客户端..."); english_text_var.set("正在初始化模型..."); chinese_text_var.set("请稍候...")
    notion_client = None
    try:
        whisper_model = whisper.load_model('base'); genai.configure(api_key=GEMINI_API_KEY); gemini_model = genai.GenerativeModel('models/gemini-2.5-flash-lite-preview-06-17');
        if NOTION_API_KEY: notion_client = Client(auth=NOTION_API_KEY)
        print("[日志] 模型与客户端初始化完毕。")
    except Exception as e: error_msg = f"模型初始化失败: {e}"; print(f"[错误] {error_msg}"); english_text_var.set(error_msg); return

    print(f"[日志] 正在尝试以弹性模式启动设备索引 {device_index} 的音频流..."); p = pyaudio.PyAudio()
    stream, sample_rate = open_resilient_stream(p, device_index)
    if not stream: error_msg = f"错误：无法为设备索引 {device_index} 打开音频流。"; print(f"[错误] {error_msg}"); english_text_var.set(error_msg); p.terminate(); return

    full_transcript_log = []; training_data_batch = []; start_time = datetime.now(); RECORD_SECONDS = 8; TARGET_RATE = 16000
    english_text_var.set("... Listening ..."); chinese_text_var.set("")
    
    while not worker_thread_stop_event.is_set():
        try:
            frames = stream.read(sample_rate * RECORD_SECONDS, exception_on_overflow=False)
            audio_data = np.frombuffer(frames, dtype=np.int16)
            audio_data_resampled = resampy.resample(audio_data.astype(float), sample_rate, TARGET_RATE) if sample_rate != TARGET_RATE else audio_data
            audio_normalized = audio_data_resampled.astype(np.float32) / 32768.0
            result = whisper_model.transcribe(audio_normalized, fp16=False)
            recognized_text = result['text'].strip()

            if recognized_text:
                english_text_var.set(recognized_text)
                chinese_text = ""
                try:
                    response = gemini_model.generate_content(f"Translate to Simplified Chinese, returning only the translation:\n{recognized_text}")
                    chinese_text = response.text.strip()
                except Exception as e:
                    print(f"[错误] Gemini翻译失败: {e}"); chinese_text = "[翻译失败]"
                
                chinese_text_var.set(chinese_text)
                
                if is_meeting_mode:
                    if chinese_text != "[翻译失败]":
                        full_transcript_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] EN: {recognized_text}\nCN: {chinese_text}\n\n")
                        training_data_batch.append({'en': recognized_text, 'cn': chinese_text})
                else: # F2 实时字幕模式
                    if chinese_text != "[翻译失败]":
                        threading.Thread(target=save_log_and_training_realtime, args=(notion_client, "实时字幕", recognized_text, chinese_text), daemon=True).start()
        except IOError as e:
            if e.errno in [-9999, -9988, -9997]: english_text_var.set("音频流中断，请重启。"); chinese_text_var.set(""); print(f"[错误] 音频流中断。"); break
            else: print(f"[错误] IO错误: {e}"); time.sleep(1)
        except Exception as e: print(f"[错误] 未知错误: {e}"); time.sleep(1)

    stream.stop_stream(); stream.close(); p.terminate()
    if is_meeting_mode and full_transcript_log:
        english_text_var.set("会议结束，正在处理..."); chinese_text_var.set("请稍候...")
        full_log_string = "".join(full_transcript_log)
        ai_summary = ""
        try:
            print("[归档流程] 步骤 1/5: 开始生成AI摘要...")
            prompt = ("你是一位专业的会议纪要分析师。请根据以下会议记录，用中文生成一份精炼的报告，包含：\n1. **核心摘要**\n2. **主要议题与结论**\n3. **会后待办事项 (Action Items)**\n\n会议记录原文:\n" f"{full_log_string}")
            summary_response = gemini_model.generate_content(prompt); ai_summary = summary_response.text.strip()
            print("[归档流程] 步骤 1/5: 成功！")
        except Exception as e: print(f"[错误] 生成AI摘要失败: {e}"); ai_summary = "AI摘要生成失败。"
        filename = f"meeting_log_{start_time.strftime('%Y-%m-%d_%H-%M-%S')}.txt"
        with open(filename, 'w', encoding='utf-8') as f: f.write(f"===== AI 会议纪要 =====\n\n--- AI 分析摘要 ---\n{ai_summary}\n\n--- 完整逐字稿 ---\n{full_log_string}")
        print(f"[日志] 完整纪要已保存到本地文件: {filename}")
        upload_meeting_and_link_all(notion_client, start_time, full_log_string, ai_summary, training_data_batch)
        english_text_var.set("归档完成！"); chinese_text_var.set("可以关闭窗口。")
    print("\n[日志] 工作线程已停止。")
    if root and root.winfo_exists():
        reset_ui_for_new_task()

def start_worker_thread(device_index, is_meeting_mode):
    global worker_thread
    if worker_thread and worker_thread.is_alive(): return
    worker_thread_stop_event.clear()
    worker_thread = threading.Thread(target=background_worker, args=(device_index, is_meeting_mode), daemon=True)
    worker_thread.start()

def on_f1_press(event=None):
    global is_meeting_running
    if not is_meeting_running:
        is_meeting_running = True
        root.unbind("<F2>")
        english_text_var.set("会议模式已启动..."); chinese_text_var.set("再按 F1 结束并生成纪要。")
        start_worker_thread(MEETING_MODE_MIC_INDEX, is_meeting_mode=True)
    else:
        english_text_var.set("正在结束会议..."); chinese_text_var.set("请稍候...")
        root.unbind("<F1>")
        worker_thread_stop_event.set() 
        is_meeting_running = False

def on_f2_press(event=None):
    root.unbind("<F1>"); root.unbind("<F2>")
    english_text_var.set("实时字幕模式已启动..."); chinese_text_var.set("")
    start_worker_thread(SUBTITLE_MODE_DEVICE_INDEX, is_meeting_mode=False)

def on_closing():
    worker_thread_stop_event.set()
    if worker_thread and worker_thread.is_alive(): worker_thread.join(timeout=3)
    root.destroy()

def reset_ui_for_new_task():
    english_text_var.set("任务已结束。"); 
    chinese_text_var.set("【F1】开始新会议 | 【F2】开始实时字幕")
    root.bind("<F1>", on_f1_press)
    root.bind("<F2>", on_f2_press)
    
def main():
    global root, english_text_var, chinese_text_var
    root = tk.Tk(); root.title("AI智能助手 v13.0")
    window_width, window_height = 900, 130;
    x_pos, y_pos = (root.winfo_screenwidth() - window_width) // 2, root.winfo_screenheight() - window_height - 60
    root.geometry(f'{window_width}x{window_height}+{x_pos}+{y_pos}'); root.overrideredirect(True); root.wm_attributes("-topmost", True); root.config(bg='#1E1E1E')
    
    # --- 【v13.0 终极UI重构】 ---
    english_text_var = tk.StringVar()
    chinese_text_var = tk.StringVar()

    frame = tk.Frame(root, bg=root.cget('bg'))
    frame.pack(expand=True, fill='both', padx=15, pady=5) # 减小垂直内边距

    # 上半部分：英文标签
    label_en = tk.Label(frame, textvariable=english_text_var, font=("微软雅黑", 16, "bold"), fg="white", bg=root.cget('bg'), justify='left', anchor='nw', wraplength=window_width-30)
    label_en.pack(side='top', fill='x', expand=True)

    # 下半部分：中文标签
    label_cn = tk.Label(frame, textvariable=chinese_text_var, font=("微软雅黑", 16), fg="#A9A9A9", bg=root.cget('bg'), justify='left', anchor='nw', wraplength=window_width-30)
    label_cn.pack(side='bottom', fill='x', expand=True)

    english_text_var.set("欢迎使用 AI 助手 v13.0")
    chinese_text_var.set("【F1】开始/结束会议 | 【F2】实时字幕")

    root.bind("<F1>", on_f1_press); root.bind("<F2>", on_f2_press); root.protocol("WM_DELETE_WINDOW", on_closing)
    print("=============================================="); print("      AI智能助手 v13.0 已启动"); print("==============================================")
    root.mainloop()

if __name__ == '__main__':
    main()