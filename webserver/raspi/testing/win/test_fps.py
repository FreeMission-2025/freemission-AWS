import cv2
import time

# URL to the MJPEG stream (your local server in this case)
url = "http://127.0.0.1/video_stream"

# Open the MJPEG stream
cap = cv2.VideoCapture(url)

if not cap.isOpened():
    print("Error: Unable to connect to stream")
else:
    # Initialize frame counter, time tracking, and FPS
    prev_time = time.time()
    frame_count = 0
    fps = 0 

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Unable to read frame")
            break
        
        # Calculate FPS every second
        current_time = time.time()
        frame_count += 1
        if current_time - prev_time >= 1:
            fps = frame_count / (current_time - prev_time)
            print(f"FPS: {fps:.2f}")
            prev_time = current_time
            frame_count = 0

        # Display the frame with FPS
        cv2.putText(frame, f"FPS: {fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Show the frame
        cv2.imshow("MJPEG Stream", frame)

        # Press 'q' to exit the video stream
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # Release the video capture object and close windows
    cap.release()
    cv2.destroyAllWindows()

