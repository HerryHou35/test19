"""
TTS Service Server — wraps espeak-ng as a ROS 2 Service.

Service: /robot_speak  (robot_programming_interfaces/srv/Speak)
  Request  — string text   : words to speak
  Response — bool success  : True if speech was queued
             string message: status or error detail

Uses espeak-ng via subprocess (NOT pyttsx3).  pyttsx3 silently fails in
headless / Gazebo environments when it cannot find an audio driver.
espeak-ng is far more reliable and reports clear errors.
"""

import subprocess
import threading

import rclpy
from rclpy.node import Node
from robot_programming_interfaces.srv import Speak

_tts_lock = threading.Lock()


class TtsServer(Node):
    def __init__(self):
        super().__init__('tts_server')

        self.srv = self.create_service(
            Speak, '/robot_speak', self._handle_speak
        )

        # Verify espeak-ng is installed
        try:
            subprocess.run(
                ['espeak-ng', '--version'],
                capture_output=True, timeout=2.0
            )
            self.get_logger().info(
                'TTS Server ready (espeak-ng) — /robot_speak service available.'
            )
        except FileNotFoundError:
            self.get_logger().fatal(
                'espeak-ng NOT FOUND!  Install it:  sudo apt install espeak-ng'
            )
        except Exception:
            self.get_logger().warn(
                'espeak-ng check failed — speech may not work.'
            )

    def _handle_speak(self, request, response):
        text = request.text.strip()
        if not text:
            response.success = False
            response.message = 'Empty text — nothing to speak.'
            return response

        self.get_logger().info(f'TTS request: "{text}"')

        thread = threading.Thread(
            target=self._speak_worker,
            args=(text,),
            daemon=True,
        )
        thread.start()

        response.success = True
        response.message = f'Queued: "{text}"'
        return response

    def _speak_worker(self, text):
        with _tts_lock:
            try:
                subprocess.run(
                    ['espeak-ng', '-v', 'en-us', '-s', '150', text],
                    timeout=30.0,
                )
            except FileNotFoundError:
                self.get_logger().error(
                    'espeak-ng not installed!  sudo apt install espeak-ng'
                )
            except Exception as e:
                self.get_logger().error(f'espeak-ng error: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = TtsServer()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
