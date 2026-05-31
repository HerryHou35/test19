import threading
import time

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from std_msgs.msg import Bool
from math import isnan, isinf
from robot_programming_interfaces.srv import Speak


class LidarFilterNode(Node):
    def __init__(self):
        super().__init__('lidar_filter_node')

        # Subscribe to the robot's native LiDAR topic
        self.scan_sub = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            10
        )

        # Publish obstacle warnings for the arbiter / voice node
        self.warning_pub = self.create_publisher(Bool, '/lidar_warning', 10)

        # ----------------------------------------------------------------
        # SERVICE CLIENT — calls /robot_speak (tts_server)
        # ----------------------------------------------------------------
        self.tts_client = self.create_client(Speak, '/robot_speak')
        if not self.tts_client.wait_for_service(timeout_sec=5.0):
            self.get_logger().error('TTS server (/robot_speak) NOT available!')
        else:
            self.get_logger().info('TTS client connected to /robot_speak.')

        # Safety parameters
        self.safe_distance = 0.3   # meters
        self.angle_range = 15      # degrees — only check the forward cone

        # TTS throttle — avoid speaking on every scan callback (~10 Hz)
        self._last_tts_time = 0.0
        self._tts_throttle = 3.0  # seconds between spoken warnings

        self.get_logger().info('LiDAR Filter Node initialized and scanning.')

    # ------------------------------------------------------------------
    # Helper: synchronous TTS call via call_async.
    # ------------------------------------------------------------------
    def _speak(self, text):
        def _do():
            req = Speak.Request()
            req.text = text
            future = self.tts_client.call_async(req)
            if not hasattr(self, '_tts_futures'):
                self._tts_futures = []
            self._tts_futures.append(future)
            self._tts_futures = [f for f in self._tts_futures if not f.done()]
        threading.Thread(target=_do, daemon=True).start()

    # ------------------------------------------------------------------
    # Scan callback
    # ------------------------------------------------------------------
    def scan_callback(self, msg):
        num_points = len(msg.ranges)
        if num_points == 0:
            return

        is_obstacle_detected = False

        for i in range(num_points):
            angle = i * (360.0 / num_points)

            # Forward cone: [0, 15] degrees  OR  [345, 360) degrees
            if angle <= self.angle_range or angle >= (360.0 - self.angle_range):
                dist = msg.ranges[i]

                if isnan(dist) or isinf(dist) or dist <= 0.0:
                    continue

                if dist < self.safe_distance:
                    is_obstacle_detected = True
                    break

        warning_msg = Bool()
        warning_msg.data = is_obstacle_detected
        self.warning_pub.publish(warning_msg)

        if is_obstacle_detected:
            self.get_logger().warn(
                'OBSTACLE DETECTED within %.2f m! Publishing /lidar_warning.' % (
                    self.safe_distance
                )
            )
            # Throttled TTS warning
            now = time.time()
            if now - self._last_tts_time >= self._tts_throttle:
                self._last_tts_time = now
                self._speak("Obstacle detected! Stopping robot.")


def main(args=None):
    rclpy.init(args=args)
    node = LidarFilterNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
