런치파일 실행후 ros2 launch slam_toolbox online_async_launch.py use_sim_time:=true 를 입력하여 slam노드실행 맵 토픽은 /map입력 qos타입은 voltile에서 transient로 바꾸어야함

nav2는 my_turtlebot_map.pgm과 my_turtlebot_map.yaml을 홈 경로로 다운로드 후 ros2 launch turtlebot3_navigation2 navigation2.launch.py use_sim_time:=true map:=/home/kimdonghwan/my_turtlebot_map.yaml 
을 사용하여 시작

제대로 실행이 안될경우 코드에있는 경로를 자신의 컴퓨터의 알맞은 파일 경로로 변경해주면 정상가동
