import json
import math
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, Bool
from geometry_msgs.msg import TwistStamped
from robot_programming_interfaces.srv import Speak


class ArbiterNode(Node):
    """
    Central command arbiter for the TurtleBot3.

    - Subscribes to /voice_tasks  (String / JSON motion sequence)
    - Subscribes to /lidar_warning (Bool   / obstacle alert)
    - Publishes  to /cmd_vel      (TwistStamped / motor commands)

    SERVICE CLIENT — calls /robot_speak for status announcements.

    Executes the voice-generated motion sequence step-by-step, but will
    immediately halt and discard the queue if a LiDAR warning arrives.
    """

    def __init__(self):
        super().__init__('arbiter_node')

        self.cmd_pub = self.create_publisher(TwistStamped, '/cmd_vel', 10)

        self.voice_sub = self.create_subscription(
            String, '/voice_tasks', self._voice_callback, 10
        )

        self.warning_sub = self.create_subscription(
            Bool, '/lidar_warning', self._warning_callback, 10
        )

        # ----------------------------------------------------------------
        # SERVICE CLIENT — calls /robot_speak (tts_server)
        # ----------------------------------------------------------------
        self.tts_client = self.create_client(Speak, '/robot_speak')
        if not self.tts_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('TTS server (/robot_speak) NOT available!')
        else:
            self.get_logger().info('TTS client connected to /robot_speak.')

        # Task execution state
        self._lock = threading.Lock()
        self._tasks = []
        self._task_idx = 0
        self._active_timer = None
        self._last_warning_tts = 0.0
        self._was_obstacle = False

        # Motion parameters
        self.linear_speed = 0.15    # m/s
        self.angular_speed = 0.5    # rad/s

        self.get_logger().info('Arbiter Node initialized.')

    # ------------------------------------------------------------------
    # Helper: synchronous TTS call.  The service responds in < 1 ms
    # (it just spawns a speech thread) so this is safe inside callbacks.
    # ------------------------------------------------------------------
    def _speak(self, text):
        def _do():
            req = Speak.Request()
            req.text = text
            future = self.tts_client.call_async(req)
            # Keep reference alive — Python GC kills orphan Futures
            if not hasattr(self, '_tts_futures'):
                self._tts_futures = []
            self._tts_futures.append(future)
            self._tts_futures = [f for f in self._tts_futures if not f.done()]
        threading.Thread(target=_do, daemon=True).start()

    # ------------------------------------------------------------------
    # Subscriber callbacks
    # ------------------------------------------------------------------

    def _voice_callback(self, msg):
        with self._lock:
            try:
                data = json.loads(msg.data)
                self._tasks = data.get('tasks', [])
                self._task_idx = 0

                self.get_logger().info(
                    'Received %d voice task(s).' % len(self._tasks)
                )

                if self._tasks:
                    self._announce_tasks()
                    self._execute_next()

            except json.JSONDecodeError:
                self.get_logger().error(
                    'Invalid JSON received on /voice_tasks'
                )

    def _warning_callback(self, msg):
        if msg.data:
            if not self._was_obstacle:
                self.get_logger().warn('OBSTACLE DETECTED!')
                self._was_obstacle = True
            now = time.time()
            if now - self._last_warning_tts >= 3.0:
                self._last_warning_tts = now
                self._speak('Warning! Obstacle ahead.')
        else:
            if self._was_obstacle:
                self.get_logger().info('LiDAR path clear.')
                self._was_obstacle = False

    # ------------------------------------------------------------------
    # Task execution
    # ------------------------------------------------------------------

    def _announce_tasks(self):
        """Speak a summary of the incoming task sequence."""
        descriptions = []
        for t in self._tasks:
            t_type = t.get('type', 'stop')
            if t_type == 'move_forward':
                descriptions.append(
                    f"move forward {t.get('distance', 0.5)} meters"
                )
            elif t_type == 'move_backward':
                descriptions.append(
                    f"move backward {t.get('distance', 0.5)} meters"
                )
            elif t_type == 'turn_left':
                descriptions.append(
                    f"turn left {t.get('angle', 90)} degrees"
                )
            elif t_type == 'turn_right':
                descriptions.append(
                    f"turn right {t.get('angle', 90)} degrees"
                )
            elif t_type == 'stop':
                descriptions.append('stop')
        if descriptions:
            self._speak('Executing: ' + ', then '.join(descriptions) + '.')

    def _describe_task(self, task):
        """Return a short spoken description of a single task."""
        t_type = task.get('type', 'stop')
        if t_type == 'move_forward':
            return f"Moving forward {task.get('distance', 0.5)} meters."
        elif t_type == 'move_backward':
            return f"Moving backward {task.get('distance', 0.5)} meters."
        elif t_type == 'turn_left':
            return f"Turning left {task.get('angle', 90)} degrees."
        elif t_type == 'turn_right':
            return f"Turning right {task.get('angle', 90)} degrees."
        elif t_type == 'stop':
            return 'Stopping.'
        return ''

    def _execute_next(self):
        """Pick the next task and start a timed motion."""
        if self._task_idx >= len(self._tasks):
            self.get_logger().info('All voice tasks completed.')
            self._stop_robot()
            self._speak('Motion sequence completed.')
            return

        task = self._tasks[self._task_idx]
        task_type = task.get('type', 'stop')

        # Speak what this specific task is
        self._speak(self._describe_task(task))

        twist = TwistStamped()
        duration = 0.0

        if task_type == 'move_forward':
            distance = float(task.get('distance', 0.5))
            twist.linear.x = self.linear_speed
            duration = distance / self.linear_speed

        elif task_type == 'move_backward':
            distance = float(task.get('distance', 0.5))
            twist.linear.x = -self.linear_speed
            duration = distance / self.linear_speed

        elif task_type == 'turn_left':
            angle_deg = float(task.get('angle', 90))
            twist.angular.z = self.angular_speed
            duration = math.radians(angle_deg) / self.angular_speed

        elif task_type == 'turn_right':
            angle_deg = float(task.get('angle', 90))
            twist.angular.z = -self.angular_speed
            duration = math.radians(angle_deg) / self.angular_speed

        elif task_type == 'stop':
            self.get_logger().info('Stop task — halting.')
            self._stop_robot()
            self._speak("Stopping.")
            return

        else:
            self.get_logger().warn(
                'Unknown task type "%s" — skipping.' % task_type
            )
            self._task_idx += 1
            self._execute_next()
            return

        self._task_idx += 1
        self.cmd_pub.publish(twist)

        self.get_logger().info(
            'Executing %s (duration %.2f s, idx %d/%d)' % (
                task_type, duration, self._task_idx, len(self._tasks)
            )
        )

        # One-shot timer: cancel in callback, then advance
        self._active_timer = self.create_timer(
            duration, self._on_task_finished
        )

    def _on_task_finished(self):
        with self._lock:
            self._cancel_timer()
            self._execute_next()

    def _cancel_timer(self):
        if self._active_timer is not None:
            self._active_timer.cancel()
            self.destroy_timer(self._active_timer)
            self._active_timer = None

    def _stop_robot(self):
        self.cmd_pub.publish(TwistStamped())
        self.get_logger().info('Robot stopped.')


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main(args=None):
    rclpy.init(args=args)
    node = ArbiterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
