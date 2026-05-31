import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from robot_programming_interfaces.srv import Speak

from ollama import Client
import sounddevice as sd
from scipy.io.wavfile import write
import whisper
import json
import threading

# ---------------------------------------------------------------------------
# WARNING: Ensure this key is stored securely.
# ---------------------------------------------------------------------------
OLLAMA_API_KEY = "e190ec7bbf1849ce96fbf545ea82b7e1.McuIbF8GqZd_sbFv-HF3heYW"
RECORD_SECONDS = 10
SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# LLM Configuration
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are a motion planner for a TurtleBot3 robot.
The user will give you a natural language movement instruction. Your job is to
break it down into a strict JSON motion sequence.

Rules:
1. Output ONLY raw JSON. Do not include any explanatory text, and do NOT wrap
   the output in markdown code blocks.
2. Every task item MUST contain a "type" field.
3. Extract precise numeric values for distance (meters) and angle (degrees).
   If the user doesn't specify a unit, use reasonable defaults (e.g., 0.5
   meters, 90 degrees).

Supported motion types and parameters:
- move_forward:  Move straight ahead.        Params: distance (float, meters)
- move_backward: Move backward.              Params: distance (float, meters)
- turn_left:     Rotate counter-clockwise.   Params: angle (int, degrees)
- turn_right:    Rotate clockwise.           Params: angle (int, degrees)
- stop:          Halt all movements.         No params

Output Format:
{
  "tasks": [ ... ]
}
"""

_client = Client(
    host="https://ollama.com",
    headers={"Authorization": f"Bearer {OLLAMA_API_KEY}"}
)


def plan_motion(text, retries=3):
    for i in range(retries):
        try:
            response = _client.chat(
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
            print(f"JSON parsing failed. Retrying {i + 1}/{retries}...")
    return {"tasks": [{"type": "stop"}]}


# ---------------------------------------------------------------------------
# ROS 2 Voice Control Node
# ---------------------------------------------------------------------------
class VoiceControlNode(Node):
    def __init__(self):
        super().__init__('voice_control_node')

        # Publish LLM-generated motion plans as JSON string
        self.task_pub = self.create_publisher(String, '/voice_tasks', 10)

        # Subscribe to LiDAR warnings for interrupt handling
        self.warning_sub = self.create_subscription(
            Bool,
            '/lidar_warning',
            self._warning_callback,
            10
        )

        # ----------------------------------------------------------------
        # SERVICE CLIENT — calls /robot_speak (tts_server)
        # ----------------------------------------------------------------
        self.tts_client = self.create_client(Speak, '/robot_speak')
        if not self.tts_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('TTS server NOT available after 5s!')
        else:
            self.get_logger().info('TTS client connected to /robot_speak.')

        self.get_logger().info('Voice Control Node initialized.')

    # ------------------------------------------------------------------
    # Helper: call the TTS service.
    # The Future MUST be stored or Python GC collects it before the
    # request is actually transmitted over DDS.
    # ------------------------------------------------------------------
    def _speak(self, text):
        req = Speak.Request()
        req.text = text
        future = self.tts_client.call_async(req)
        future.add_done_callback(self._on_tts_done)
        # Keep a reference so GC doesn't kill the future mid-flight
        if not hasattr(self, '_tts_futures'):
            self._tts_futures = []
        self._tts_futures.append(future)
        self._tts_futures = [f for f in self._tts_futures if not f.done()]

    def _on_tts_done(self, future):
        if future.exception() is not None:
            self.get_logger().error(f'TTS call failed: {future.exception()}')

    def _warning_callback(self, msg):
        if msg.data:
            self.get_logger().warn('LiDAR warning received!')
            # Do NOT publish stop — the user is in control.
            # The arbiter and lidar_filter already handle TTS warnings.

    def publish_tasks(self, tasks_dict):
        msg = String()
        msg.data = json.dumps(tasks_dict)
        self.task_pub.publish(msg)
        self.get_logger().info(f'Published voice tasks: {msg.data}')


# ---------------------------------------------------------------------------
# Voice pipeline (runs in background thread)
# ---------------------------------------------------------------------------
def voice_pipeline(node):
    print("=" * 40)
    print("  TurtleBot3 Radar-Based Voice Control")
    print("=" * 40)

    print("Loading Whisper model...")
    whisper_model = whisper.load_model("base")
    print("System Ready\n")

    # Wait a moment for TTS server to become available
    if not node.tts_client.wait_for_service(timeout_sec=5.0):
        node.get_logger().warn('TTS server did not appear — continuing without speech.')
    node._speak("System ready. Please give me a motion command.")

    while rclpy.ok():
        try:
            user_input = input(
                "\n[Press Enter to Speak | Type 'test_lidar' for radar test]: "
            )

            if user_input.strip() == "test_lidar":
                node._speak("This is a test of the TTS warning system.")
                continue

            # Record audio
            print(f"Recording ({RECORD_SECONDS} seconds)...")
            audio = sd.rec(
                int(RECORD_SECONDS * SAMPLE_RATE),
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16"
            )
            sd.wait()
            write("input.wav", SAMPLE_RATE, audio)

            # Speech-to-text
            print("Transcribing...")
            result = whisper_model.transcribe("input.wav", language="en")
            text = result["text"].strip()
            print(f"Transcription: {text}")

            if not text:
                print("No speech detected.")
                continue

            # LLM motion planning
            print("Planning motions...")
            tasks = plan_motion(text)

            print("\nGenerated Motion Sequence:")
            print(json.dumps(tasks, ensure_ascii=False, indent=2))

            # Publish to arbiter via /voice_tasks
            node.publish_tasks(tasks)

            if tasks.get("tasks") and tasks["tasks"][0]["type"] != "stop":
                node._speak(f"Executing command: {text}.")
            else:
                node._speak("Command received: stop.")

        except KeyboardInterrupt:
            print("\nExiting voice pipeline...")
            break
        except Exception as e:
            print(f"Error encountered: {e}")

    rclpy.shutdown()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(args=None):
    rclpy.init(args=args)
    node = VoiceControlNode()

    # Start voice pipeline in a daemon thread
    voice_thread = threading.Thread(
        target=voice_pipeline,
        args=(node,),
        daemon=True
    )
    voice_thread.start()

    # Main thread runs ROS callbacks (lidar_warning subscriber, etc.)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
