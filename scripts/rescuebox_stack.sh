#!/usr/bin/env bash
set -eo pipefail

LOG_TAG="[rescuebox_stack]"
echo "$LOG_TAG starting..."

source /opt/ros/jazzy/setup.bash
source /home/rescue-pi/work/rescuebox_ws/install/setup.bash

sleep 2

ros2 launch rescuebox text_to_speech.launch.xml &
PID_TTS=$!

ros2 launch rescuebox microphone_publisher.launch.xml &
PID_MIC=$!

ros2 launch rescuebox chatbot.launch.xml &
PID_CHATBOT=$!

sleep 3

ros2 launch rescuebox speech_to_text.launch.xml &
PID_STT=$!

sleep 2
ros2 launch rescuebox assessment_client.launch.xml &
PID_ASSESS=$!

echo "$LOG_TAG started. PIDs: tts=$PID_TTS mic=$PID_MIC player=$PID_PLAYER chatbot=$PID_CHATBOT stt=$PID_STT assess=$PID_ASSESS"

wait
