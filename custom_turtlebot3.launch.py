import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.actions import SetEnvironmentVariable
from launch.actions import ExecuteProcess
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

def generate_launch_description():
    user_home = os.path.expanduser('~') # 실행하는 사용자의 홈 디렉토리를 자동으로 찾도록 수정
    # [경로 오류 해결] 맵 파일이 위치한 정확한 전체 경로로 수정합니다.
    world_file_path = os.path.join(user_home, 'turtlebot_ws', 'src', 'Robot-programming', 'turtlebot3_custom_maps', 'my_square_world.world')
    
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    pkg_turtlebot3_desc = get_package_share_directory('turtlebot3_description')
    pkg_turtlebot3_gazebo = get_package_share_directory('turtlebot3_gazebo')
    pkg_slam_toolbox = get_package_share_directory('slam_toolbox')

    # 1. 가제보 하모닉 실행 (우리 커스텀 맵 로드)
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': f'-r {world_file_path}'}.items(),
    )

    # 2. 로봇 상태 발행기 (ROS 2 Rviz 및 TF 좌표계용 URDF 로드)
    urdf_file = os.path.join(pkg_turtlebot3_desc, 'urdf', 'turtlebot3_burger.urdf')
    with open(urdf_file, 'r') as infp:
        robot_desc = infp.read()

    robot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{
            'use_sim_time': True,
            'robot_description': robot_desc
        }],
    )

    # 3. 가제보 스폰: '공식 Gazebo SDF 모델' 다이렉트 로드
    model_sdf_path = os.path.join(pkg_turtlebot3_gazebo, 'models', 'turtlebot3_burger', 'model.sdf')
    
    gz_spawn_robot = Node(
        package='ros_gz_sim',
        executable='create',
        output='screen',
        arguments=[
            '-world', 'my_square_world',
            '-file', model_sdf_path,
            '-name', 'turtlebot3_burger',
            '-x', '0.3', '-y', '0.3', '-z', '0.05'
        ],
    )

    # 기본 제공되는 터틀봇3 RViz 설정 파일 경로 추가
    rviz_config_path = os.path.join(pkg_turtlebot3_desc, 'rviz', 'model.rviz')

    # 4. RViz2 노드 추가 (자율주행 및 맵핑 시각화용)
    rviz2_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        parameters=[{'use_sim_time': True}],
        arguments=['-d', rviz_config_path],
    )

    # 5. ROS 2 <=> 가제보 통신 브릿지 (최종 연결 완료)
    gz_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        output='screen',
        # parameters=[{'use_sim_time': True}], # [삭제] 브릿지 본인에게 가상 시간을 먹이면 타임루프 오류가 발생합니다!
        arguments=[
            # [진짜 진짜 최종 수정 😭] ROS 2에서 가제보로 조종 신호를 '보내는(->)' 것이므로 반드시 ']' 기호를 써야 합니다!
            '/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist',
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock',
            
            # [핵심 수정] 드디어 찾아낸 가제보 실제 라이다 주소(/scan)를 직결!
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan',
            
            # [매핑 필수 추가] 로봇의 이동 경로를 알려주는 오도메트리(Odometry) 브릿지 추가
            '/model/turtlebot3_burger/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry',
            
            '/model/turtlebot3_burger/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V'
        ],
        remappings=[
            # 가제보 이름과 ROS 2 이름이 /scan으로 이미 동일하므로 리맵핑 유지(또는 생략 가능)
            ('/scan', '/scan'),
            ('/model/turtlebot3_burger/odometry', '/odom'), # 가제보 오도메트리를 ROS 2 /odom으로 연결
            ('/model/turtlebot3_burger/tf', '/tf')
        ]
    )

    # 6. SLAM Toolbox 실행 (진짜 지도를 그리는 노드)
    slam_toolbox = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            os.path.join(pkg_slam_toolbox, 'config', 'mapper_params_online_async.yaml'),
            {
                'use_sim_time': True,              # 현실 시간(Wall time) 사용 절대 금지, 무조건 가제보 시간 사용!
                'transform_timeout': 3.0,          # 노트북 렉으로 인한 시간 지연 1초까지 너그럽게 허용
                'odom_frame': 'odom',
                'base_frame': 'base_footprint'
            }
        ]
    )

    # 7. 제스처 제어 파이썬 스크립트 직접 실행 (네트워크 단절 완벽 해결)
    # MediaPipe 기반의 새로운 제스처 코드가 실행되도록 경로를 수정합니다.
    # gesture_script_path = os.path.join(user_home, 'turtlebot_ws', 'src', 'Robot-programming', 'gesture_teleop_mediapipe', 'gesture_teleop_mediapipe.py')
    # gesture_node = ExecuteProcess(
    #     cmd=['python3', gesture_script_path],
    #     output='screen',
    #     cwd=os.path.dirname(gesture_script_path)
    # )

    # 8. WASD 키보드 조종 노드 실행 (키보드 입력을 받기 위해 새 터미널 창을 자동으로 띄움)
    wasd_script_path = os.path.join(user_home, 'turtlebot_ws', 'src', 'Robot-programming', 'wasd_teleop.py')
    wasd_node = ExecuteProcess(
        cmd=['gnome-terminal', '--', 'bash', '-c', f'export ROS_LOCALHOST_ONLY=1 && python3 {wasd_script_path}'],
        output='screen'
    )

    return LaunchDescription([
        # [공용 와이파이 환경 대응] 멀티캐스트가 막힌 네트워크에서 컴퓨터 내부 통신만 허용하여 데이터 누락 방지
        SetEnvironmentVariable(name='ROS_LOCALHOST_ONLY', value='1'),
        # [가제보 통신 에러 방지] 가제보 내부 통신도 로컬호스트(127.0.0.1)로 강제하여 create 무한 대기 에러 해결
        SetEnvironmentVariable(name='GZ_IP', value='127.0.0.1'),
        
        gz_sim,
        robot_state_publisher,
        gz_spawn_robot,
        rviz2_node, # RViz2 추가
        gz_bridge,
        slam_toolbox, # SLAM 매핑 추가
        # gesture_node, # 런치 파일 하나로 제스처 컨트롤까지 동시 실행! (주석 처리됨)
        wasd_node # 새 창에서 WASD 조종기 실행
    ])
