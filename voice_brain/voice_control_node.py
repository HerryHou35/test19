from ollama import Client
import sounddevice as sd
from scipy.io.wavfile import write
import whisper
import json
import pyttsx3
import threading  # 引入多线程库，解决 pyttsx3 阻塞卡死问题

# WARNING: Ensure this key is stored securely
OLLAMA_API_KEY = "e190ec7bbf1849ce96fbf545ea82b7e1.McuIbF8GqZd_sbFv-HF3heYW"
RECORD_SECONDS = 10
SAMPLE_RATE = 16000

# 初始化全局语音锁，防止多个线程同时说话导致声音重叠或报错
tts_lock = threading.Lock()


# ─── 异步语音播报核心逻辑 ──────────────────────────
def _say_worker(text):
    """在子线程中安全运行的语音播报函数"""
    with tts_lock:
        try:
            # 每次播报前在子线程内独立初始化引擎，彻底解决多线程上下文崩溃问题
            engine = pyttsx3.init()
            voices = engine.getProperty('voices')
            for voice in voices:
                if "EN" in voice.id.upper() or "ENGLISH" in voice.id.upper():
                    engine.setProperty('voice', voice.id)
                    break
            engine.setProperty('rate', 150)

            engine.say(text)
            engine.runAndWait()
            # 释放底层组件
            del engine
        except Exception as e:
            print(f"\n❌ TTS Thread Error: {e}")


def robot_speak(text):
    """主程序调用的非阻塞语音接口"""
    print(f"\n🤖 Robot Voice Feedback: '{text}'")
    # 启动独立线程去说话，主线程立刻解放，可以继续响应雷达或键盘
    t = threading.Thread(target=_say_worker, args=(text,), daemon=True)
    t.start()


# ─── LLM 配置 ───────────────────────────────────────
SYSTEM_PROMPT = """
You are a motion planner for a TurtleBot3 robot.
The user will give you a natural language movement instruction. Your job is to break it down into a strict JSON motion sequence.

Rules:
1. Output ONLY raw JSON. Do not include any explanatory text, and do NOT wrap the output in markdown code blocks.
2. Every task item MUST contain a "type" field. 
3. Extract precise numeric values for distance (meters) and angle (degrees). If the user doesn't specify a unit, use reasonable defaults (e.g., 0.5 meters, 90 degrees).

Supported motion types and parameters:
- move_forward:  Move straight ahead.          Params: distance (float, in meters)
- move_backward: Move backward.                 Params: distance (float, in meters)
- turn_left:     Rotate counter-clockwise.     Params: angle (int, in degrees)
- turn_right:    Rotate clockwise.             Params: angle (int, in degrees)
- stop:          Halt all movements immediately. No params

Output Format:
{
  "tasks": [ ... ]
}
"""

client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"}
)


def plan_motion(text, retries=3):
    for i in range(retries):
        try:
            response = client.chat(
                model="gpt-oss:120b",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ]
            )
            raw = response["message"]["content"].strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            tasks = json.loads(raw)
            return tasks
        except json.JSONDecodeError:
            print(f"⚠️  JSON parsing failed. Retrying {i + 1}/{retries}...")
    return {"tasks": [{"type": "stop"}]}


# ─── 雷达障碍物触发回调 ─────────────────────────────
def on_lidar_obstacle_detected():
    robot_speak("Warning! Path blocked by an obstacle. Stopping the robot.")


# ─── 主流程 ──────────────────────────────────────────
def main():
    print("=" * 40)
    print("  TurtleBot3 Radar-Based Voice Control")
    print("=" * 40)

    print("⏳ Loading Whisper model...")
    whisper_model = whisper.load_model("base")
    print("✅ System Ready\n")

    # 启动时打招呼
    robot_speak("System ready. Please give me a motion command.")

    while True:
        # 为了不让 input() 把整个进程死锁，加个小提示
        user_input = input("\n[Press Enter to Speak | Type 'test_lidar' for radar test]: ")

        if user_input.strip() == "test_lidar":
            on_lidar_obstacle_detected()
            continue

        try:
            # 录音
            print(f"🎤 Recording ({RECORD_SECONDS} seconds)...")
            audio = sd.rec(int(RECORD_SECONDS * SAMPLE_RATE),
                           samplerate=SAMPLE_RATE, channels=1, dtype="int16")
            sd.wait()
            write("input.wav", SAMPLE_RATE, audio)

            # STT
            print("🔍 Transcribing...")
            result = whisper_model.transcribe("input.wav", language="en")
            text = result["text"].strip()
            print(f"📝 Transcription: {text}")

            if not text:
                print("⚠️  No speech detected.")
                continue

            # LLM 规划
            print("🧠 Planning motions...")
            tasks = plan_motion(text)

            print("\n📋 Generated Motion Sequence:")
            print(json.dumps(tasks, ensure_ascii=False, indent=2))

            # 成功解析出动作后播报
            if tasks.get("tasks") and tasks["tasks"][0]["type"] != "stop":
                robot_speak("Executing motion commands.")

        except KeyboardInterrupt:
            print("\n👋 Exiting.")
            break
        except Exception as e:
            print(f"❌ Error encountered: {e}")


if __name__ == "__main__":
    main()
