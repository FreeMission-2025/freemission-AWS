'''
    Inference with NMS embedded on the model (Nvidia TensorRT , Cuda and CPU)
'''
import cv2
import numpy as np
import onnxruntime
import time
import os

# Load cuda and cudnn dlls. If not installed, import torch with CUDA support before import onnxruntime
cuda_path = os.path.join(os.environ["CUDA_PATH"], "bin")
onnxruntime.preload_dlls(cuda=True, cudnn=True, directory=cuda_path)
onnxruntime.print_debug_info()

# Initialize the ONNX Runtime session
model_path = './model/onnx/v11_s_a.onnx'
sess_options = onnxruntime.SessionOptions()
sess_options.log_severity_level = 1
session = onnxruntime.InferenceSession(model_path, sess_options, providers=['CUDAExecutionProvider', 'CPUExecutionProvider']) #TensorrtExecutionProvider

# get the outputs metadata as a list of :class:`onnxruntime.NodeArg`
output_name = session.get_outputs()[0].name

# get the inputs metadata as a list of :class:`onnxruntime.NodeArg`
input_name = session.get_inputs()[0].name

class_names = ['smoke', 'fire']  

def preprocess(image, input_size=(640, 640)):
    """
    Preprocess the image: convert BGR to RGB, resize, normalize, and reformat dimensions.
    """
    # Convert to RGB
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    # Resize to model input size
    resized = cv2.resize(image_rgb, input_size)
    # Normalize (0-255 -> 0-1)
    normalized = resized.astype(np.float32) / 255.0
    # Change shape from (H, W, C) to (C, H, W)
    transposed = np.transpose(normalized, (2, 0, 1))
    # Add batch dimension: (1, C, H, W)
    input_tensor = np.expand_dims(transposed, axis=0)
    return input_tensor

def postprocess(outputs, conf_threshold):
    """
    Postprocess ONNX model output with expected output shape (1, 300, 6).
    """
    # Remove the batch dimension: shape becomes (300, 6)
    detections = np.squeeze(outputs[0], axis=0)
    
    boxes = []
    for det in detections:
        # det is expected to be an array with 6 elements: [x1, y1, x2, y2, score, class_id]
        x1, y1, x2, y2, score, class_id = det
        
        if score >= conf_threshold:
            boxes.append([x1, y1, x2, y2, score, int(class_id)])
            
    return boxes

# Open a connection to the webcam
image_path = './sample.jpg'  # <-- replace with your image path
frame = cv2.imread(image_path)

if frame is None:
    raise FileNotFoundError(f"Image not found: {image_path}")

try:
    # Preprocess the frame to match model input
    input_tensor = preprocess(frame, input_size=(640, 640))

    # Run inference with the ONNX model
    outputs = session.run([output_name], {input_name: input_tensor})

    # Postprocess outputs: filter detections by confidence
    detections = postprocess(outputs, conf_threshold=0.25)


    # Draw detections on the original frame
    for det in detections:
        x1, y1, x2, y2, score, class_id = det

        # If the model's coordinates are based on the resized input,
        # scale them back to the original frame dimensions:
        h_orig, w_orig = frame.shape[:2]
        x_scale = w_orig / 640
        y_scale = h_orig / 640
        x1 = int(x1 * x_scale)
        y1 = int(y1 * y_scale)
        x2 = int(x2 * x_scale)
        y2 = int(y2 * y_scale)

        # Draw the bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{class_names[class_id]}: {score:.2f}"
        cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Display the frame with drawn detections
    cv2.imwrite("output.jpg", frame)
    print("Image saved as output.jpg")
except Exception as e:
    print(f"An unexpected error occurred: {e}")
