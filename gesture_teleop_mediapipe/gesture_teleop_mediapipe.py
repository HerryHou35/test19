import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'  # 보기 싫은 텐서플로우 경고 로그 완벽히 숨기기
os.environ['PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION'] = 'python' # MediaPipe Protobuf C++ 충돌 버그 우회

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import cv2
import mediapipe as mp
import urllib.request
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

class GestureTeleopMediapipe(Node):
    def __init__(self):
        super().__init__('gesture_teleop_mediapipe')
        
        # 1. 속도 제어 토픽 퍼블리셔
        self.publisher_ = self.create_publisher(Twist, 'cmd_vel', 10)
        
        # 2. MediaPipe Tasks API (최신 방식) 초기화
        self.model_path = 'hand_landmarker.task'
        if not os.path.exists(self.model_path):
            self.get_logger().info("AI 모델(hand_landmarker.task)을 다운로드합니다... (최초 1회)")
            url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'
            urllib.request.urlretrieve(url, self.model_path)
            self.get_logger().info("다운로드 완료!")
            
        base_options = python.BaseOptions(model_asset_path=self.model_path)
        options = vision.HandLandmarkerOptions(base_options=base_options, num_hands=1)
        self.detector = vision.HandLandmarker.create_from_options(options)
        
        # 3. 카메라 켜기
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cv2.namedWindow("MediaPipe Gesture Control", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("MediaPipe Gesture Control", 960, 540)
        
        self.timer = self.create_timer(0.1, self.timer_callback)
        self.get_logger().info("MediaPipe 준비 완료! 손가락 개수로 조종하세요.")

    def timer_callback(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        # 거울 모드 반전 및 BGR을 RGB로 변환 (MediaPipe는 RGB를 사용)
        frame = cv2.flip(frame, 1)
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # MediaPipe 최신 Tasks API로 손 인식 실행!
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        results = self.detector.detect(mp_image)
        
        command = "Nothing"
        
        # 화면에 손이 감지되었다면
        if results.hand_landmarks:
            for hand_landmarks in results.hand_landmarks:
                # 화면에 뼈대 직접 그리기 (에러가 나던 solutions 모듈 없이 자체 구현)
                h, w, _ = frame.shape
                connections = [(0,1), (1,2), (2,3), (3,4), (5,6), (6,7), (7,8), (9,10), (10,11), (11,12), (13,14), (14,15), (15,16), (17,18), (18,19), (19,20), (0,5), (5,9), (9,13), (13,17), (0,17)]
                
                for pt in hand_landmarks:
                    cv2.circle(frame, (int(pt.x * w), int(pt.y * h)), 5, (0, 0, 255), -1)
                for conn in connections:
                    pt1, pt2 = hand_landmarks[conn[0]], hand_landmarks[conn[1]]
                    cv2.line(frame, (int(pt1.x * w), int(pt1.y * h)), (int(pt2.x * w), int(pt2.y * h)), (0, 255, 0), 2)
                
                # 각 손가락이 펴졌는지(1) 접혔는지(0)를 저장할 리스트: [엄지, 검지, 중지, 약지, 소지]
                fingers_status = []
                
                # 1. 엄지손가락 (Thumb) 확인
                if hand_landmarks[4].x < hand_landmarks[3].x:
                    fingers_status.append(1)
                else:
                    fingers_status.append(0)
                
                # 2. 나머지 네 손가락 확인 (y좌표로 위아래 비교)
                for tip, mid in zip([8, 12, 16, 20], [6, 10, 14, 18]):
                    if hand_landmarks[tip].y < hand_landmarks[mid].y:
                        fingers_status.append(1)
                    else:
                        fingers_status.append(0)
                
                # 🎨 내가 원하는 나만의 제스처 만들기!
                if fingers_status == [0, 0, 0, 0, 0]:
                    command = "Stop"       # 주먹 쥐기
                elif fingers_status == [0, 1, 0, 0, 0]:
                    command = "Forward"    # 검지만 펴기 (숫자 1 모양)
                elif fingers_status == [0, 0, 0, 0, 1]:
                    command = "Right"      # 가위 모양 (V 사인)
                elif fingers_status == [1, 0, 0, 0, 0]:
                    command = "Left"       # 엄지, 검지 펴기
                elif fingers_status == [1, 1, 1, 0, 0]:
                    command = "Backward"   # 엄지, 검지, 소지 펴기)
                elif sum(fingers_status) >= 4:
                    command = "Forward"       # 손을 쫙 펴면 (보) 정지

        # 4. 명령에 따라 로봇 이동
        twist = Twist()
        if command == "Forward":
            twist.linear.x = 0.15
        elif command == "Backward":
            twist.linear.x = -0.15
        elif command == "Left":
            twist.angular.z = 0.5
        elif command == "Right":
            twist.angular.z = -0.5
        elif command == "Stop":
            twist.linear.x = 0.0
            twist.angular.z = 0.0
            
        self.publisher_.publish(twist)

        # 화면에 상태 표시
        cv2.putText(frame, f"Cmd: {command}", (20, 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
        cv2.imshow("MediaPipe Gesture Control", frame)
        cv2.waitKey(1)

def main(args=None):
    rclpy.init(args=args)
    node = GestureTeleopMediapipe()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.publisher_.publish(Twist()) # 종료 시 정지
        node.cap.release()
        cv2.destroyAllWindows()
        rclpy.shutdown()

if __name__ == '__main__':
    main()