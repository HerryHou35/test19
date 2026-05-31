import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python'

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import TwistStamped
import cv2
import mediapipe as mp
import numpy as np
import urllib.request
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


class GestureTeleopMediapipe(Node):
    def __init__(self):
        super().__init__('gesture_teleop_mediapipe')

        # Velocity command publisher
        self.publisher_ = self.create_publisher(TwistStamped, 'cmd_vel', 10)

        # MediaPipe Tasks API: download model to a stable location
        model_dir = os.path.join(os.path.expanduser('~'), '.mediapipe_models')
        os.makedirs(model_dir, exist_ok=True)
        self.model_path = os.path.join(model_dir, 'hand_landmarker.task')

        if not os.path.exists(self.model_path):
            self.get_logger().info(
                'Downloading hand_landmarker.task (one-time)...'
            )
            url = (
                'https://storage.googleapis.com/mediapipe-models/'
                'hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
            )
            urllib.request.urlretrieve(url, self.model_path)
            self.get_logger().info('Download complete!')

        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.HandLandmarkerOptions(
            base_options=base_options, num_hands=1
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        # Camera
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.get_logger().error(
                'Cannot open camera /dev/video0! '
                'Is a webcam connected?'
            )
        else:
            self.get_logger().info('Camera opened successfully.')
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # OpenCV window — force it to appear even in headless-ish contexts
        cv2.namedWindow('MediaPipe Gesture Control', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('MediaPipe Gesture Control', 960, 540)
        try:
            cv2.setWindowProperty(
                'MediaPipe Gesture Control',
                cv2.WND_PROP_TOPMOST, 1
            )
        except Exception:
            pass  # TOPMOST not supported on all window managers

        self.timer = self.create_timer(0.1, self.timer_callback)
        self.get_logger().info(
            'MediaPipe gesture teleop ready. Use finger-count gestures.'
        )

    def timer_callback(self):
        ret, frame = self.cap.read()
        if not ret:
            # Show a placeholder so the window is visible even without camera
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(
                frame, 'NO CAMERA', (140, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 0, 255), 3
            )
            cv2.imshow('MediaPipe Gesture Control', frame)
            cv2.waitKey(1)
            return

        # Mirror + RGB conversion
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        results = self.detector.detect(mp_image)

        command = 'Nothing'

        if results.hand_landmarks:
            for hand_landmarks in results.hand_landmarks:
                h, w, _ = frame.shape
                connections = [
                    (0, 1), (1, 2), (2, 3), (3, 4),
                    (5, 6), (6, 7), (7, 8),
                    (9, 10), (10, 11), (11, 12),
                    (13, 14), (14, 15), (15, 16),
                    (17, 18), (18, 19), (19, 20),
                    (0, 5), (5, 9), (9, 13), (13, 17), (0, 17)
                ]

                for pt in hand_landmarks:
                    cv2.circle(
                        frame, (int(pt.x * w), int(pt.y * h)),
                        5, (0, 0, 255), -1
                    )
                for conn in connections:
                    pt1 = hand_landmarks[conn[0]]
                    pt2 = hand_landmarks[conn[1]]
                    cv2.line(
                        frame,
                        (int(pt1.x * w), int(pt1.y * h)),
                        (int(pt2.x * w), int(pt2.y * h)),
                        (0, 255, 0), 2
                    )

                # Finger states: [thumb, index, middle, ring, pinky]
                fingers_status = []

                # Thumb
                if hand_landmarks[4].x < hand_landmarks[3].x:
                    fingers_status.append(1)
                else:
                    fingers_status.append(0)

                # Other four fingers
                for tip, mid in zip([8, 12, 16, 20], [6, 10, 14, 18]):
                    if hand_landmarks[tip].y < hand_landmarks[mid].y:
                        fingers_status.append(1)
                    else:
                        fingers_status.append(0)

                # Gesture mapping
                if fingers_status == [0, 0, 0, 0, 0]:
                    command = 'Stop'           # fist
                elif fingers_status == [0, 1, 0, 0, 0]:
                    command = 'Forward'        # index only
                elif fingers_status == [0, 0, 0, 0, 1]:
                    command = 'Right'          # pinky only
                elif fingers_status == [1, 0, 0, 0, 0]:
                    command = 'Left'           # thumb only
                elif fingers_status == [1, 1, 1, 0, 0]:
                    command = 'Backward'       # three fingers
                elif sum(fingers_status) >= 4:
                    command = 'Forward'        # open palm

        # Publish velocity (TwistStamped for real TurtleBot3 hardware)
        twist_msg = TwistStamped()
        twist_msg.header.stamp = self.get_clock().now().to_msg()
        twist_msg.header.frame_id = 'base_link'

        if command == 'Forward':
            twist_msg.twist.linear.x = 0.15
        elif command == 'Backward':
            twist_msg.twist.linear.x = -0.15
        elif command == 'Left':
            twist_msg.twist.angular.z = 0.5
        elif command == 'Right':
            twist_msg.twist.angular.z = -0.5
        elif command == 'Stop':
            twist_msg.twist.linear.x = 0.0
            twist_msg.twist.angular.z = 0.0

        # Only publish when a hand is detected ("Nothing" = no hand → stay quiet,
        # so voice control via arbiter can take over /cmd_vel).
        if command != 'Nothing':
            self.publisher_.publish(twist_msg)

        cv2.putText(
            frame, f'Cmd: {command}', (20, 50),
            cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3
        )
        cv2.imshow('MediaPipe Gesture Control', frame)
        cv2.waitKey(1)


def main(args=None):
    rclpy.init(args=args)
    node = GestureTeleopMediapipe()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publisher_.publish(TwistStamped())  # stop on exit
        node.cap.release()
        cv2.destroyAllWindows()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
