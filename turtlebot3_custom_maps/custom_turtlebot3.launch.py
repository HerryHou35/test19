import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node

def generate_launch_description():
    user_home = '/home/kimdonghwan'
    world_file_path = os.path.join(user_home, 'turtlebot3_custom_maps', 'my_square_world.world')
    pkg_slam_toolbox = get_package_share_directory('slam_toolbox')
    default_slam_params = os.path.join(pkg_slam_toolbox, 'config', 'mapper_params_online_async.yaml')
    pkg_ros_gz_sim = get_package_share_directory('ros_gz_sim')
    pkg_turtlebot3_desc = get_package_share_directory('turtlebot3_description')
    pkg_turtlebot3_gazebo = get_package_share_directory('turtlebot3_gazebo')

    # 1. 가제보 하모닉 실행
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_ros_gz_sim, 'launch', 'gz_sim.launch.py')
        ),
        launch_arguments={'gz_args': f'-r {world_file_path}'}.items(),
    )

    # 2. 로봇 상태 발행기 (URDF 로드) 
    urdf_file = os.path.join(pkg_turtlebot3_desc, 'urdf', 'turtlebot3_burger.urdf') 
    with open(urdf_file, 'r') as infp: 
        # 파일 내용을 읽은 뒤, 문자열 내의 '${namespace}'를 빈 칸으로 지워버립니다.
        robot_desc = infp.read().replace('${namespace}', '') 

    # [핵심 수술 부위] frame_prefix를 추가하여 가제보와 이름을 자동 통일! 
    robot_state_publisher = Node( 
        package='robot_state_publisher', 
        executable='robot_state_publisher', 
        name='robot_state_publisher', 
        output='screen', 
        parameters=[{ 
            'use_sim_time': True, 
            'robot_description': robot_desc, 
            'frame_prefix': 'turtlebot3_burger/'  
        }], 
    )

    # 3. 가제보 스폰
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
        parameters=[{'use_sim_time': True}]
    )

    # 4. RViz2 노드
    rviz2_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        parameters=[{'use_sim_time': True}],
    )

   # 5. ROS 2 <=> 가제보 통신 브릿지 
    gz_bridge = Node( 
        package='ros_gz_bridge', 
        executable='parameter_bridge', 
        output='screen', 
        arguments=[ 
            # 🔥 1. 수정됨: 가제보의 정식 주소로 브릿지 연결
            '/model/turtlebot3_burger/cmd_vel@geometry_msgs/msg/Twist]gz.msgs.Twist', 
            '/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock', 
            '/scan@sensor_msgs/msg/LaserScan[gz.msgs.LaserScan', 
            '/model/turtlebot3_burger/tf@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V', 
            '/world/my_square_world/model/turtlebot3_burger/joint_state@sensor_msgs/msg/JointState[gz.msgs.Model', 
            '/model/turtlebot3_burger/odometry@nav_msgs/msg/Odometry[gz.msgs.Odometry' 
        ], 
        remappings=[ 
            # 🔥 2. 추가됨: ROS 2의 /cmd_vel 토픽을 가제보 정식 주소와 매핑
            ('/model/turtlebot3_burger/cmd_vel', '/cmd_vel'),
            ('/scan', '/scan'), 
            ('/model/turtlebot3_burger/tf', '/tf'), 
            ('/world/my_square_world/model/turtlebot3_burger/joint_state', '/joint_states'), 
            ('/model/turtlebot3_burger/odometry', '/odom')  
        ], 
        parameters=[{'use_sim_time': True}] 
    )
    # 🔥 여기가 빠져있었습니다! 7. 라이다 프레임 연결용 Static TF 정의 🔥
    # 반드시 return 구문보다 위쪽에 있어야 합니다.
    lidar_static_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='lidar_static_tf',
        arguments=['0', '0', '0', '0', '0', '0', 'turtlebot3_burger/base_scan', 'base_scan'],
        output='screen'
    )
	# 🔥 8. (신규 추가) SLAM 고집 꺾기용 마법의 Static TF 🔥
    # SLAM이 애타게 찾는 옛날 이름(base_footprint)을 우리 로봇에 강제로 이어붙여 세상을 속입니다!
    slam_hack_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='slam_hack_tf',
        arguments=['0', '0', '0', '0', '0', '0', 'turtlebot3_burger/base_footprint', 'base_footprint'],
        output='screen'
    )

  # 🔥 9. (신규 추가) Nav2용 base_link Static TF 🔥
    # Nav2가 애타게 찾는 base_link를 우리 로봇 중심에 강제로 이어붙입니다!
    nav2_hack_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='nav2_hack_tf',
        arguments=['0', '0', '0', '0', '0', '0', 'turtlebot3_burger/base_link', 'base_link'],
        output='screen'
    )

    # 마무리 배열에 추가
    return LaunchDescription([ 
        gz_sim, 
        robot_state_publisher, 
        gz_spawn_robot, 
        rviz2_node, 
        gz_bridge,
        lidar_static_tf,
        slam_hack_tf,
        nav2_hack_tf   # 🔥 여기 추가!
    ])
