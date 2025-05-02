import cv2
import numpy as np
import os
from inference import ShmQueue
from utils.logger import Log

isOnnxInstalled = False
try:
    import onnxruntime
    isOnnxInstalled = True
except ImportError:
    print("__inference:12 : onnxruntime package not installed")

def get_onnx_status():
    return isOnnxInstalled

class ObjectDetection:
    """
    Initialize the ObjectDetection class.
    
    :param model_path: Path to the ONNX model
    :param input_queue: Input queue where frames will be processed
    :param output_queue: Output queue where processed frame will be stored
    :param input_size: The input size for the model (width, height)
    :param conf_threshold: Confidence threshold for filtering detections
    :param class_names: List of class names
    """
    def __init__(self, model_path: str, input_queue: ShmQueue, output_queue: ShmQueue, input_size=(640, 640), conf_threshold=0.25, class_names=None):
        if not isOnnxInstalled:
            raise RuntimeError("Onnxruntime Is Not Installed")
        
        # Load cuda and cudnn dlls
        cuda_path = os.path.join(os.environ.get("CUDA_PATH", ""), "bin")
        if cuda_path:
            onnxruntime.preload_dlls(cuda=True, cudnn=True, directory=cuda_path)

        self.input_queue  = input_queue
        self.output_queue = output_queue
        
        # Initialize the ONNX Runtime session
        self.model_path = model_path
        self.sess_options = onnxruntime.SessionOptions()
        self.sess_options.log_severity_level = 1
        self.session = onnxruntime.InferenceSession(model_path, self.sess_options, 
                                                    providers=['CUDAExecutionProvider', 'CPUExecutionProvider'])

        # Get input and output names
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name

        # Set class names
        self.class_names = class_names if class_names else ['smoke', 'fire']
        self.input_size = input_size
        self.conf_threshold = conf_threshold

    def preprocess(self, image: cv2.typing.MatLike):
        """
        Preprocess the image: convert BGR to RGB, resize, normalize, and reformat dimensions.
        
        :param image: Input image to preprocess
        :return: Preprocessed image as a tensor
        """
        # Convert to RGB
        image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        # Resize to model input size
        resized = cv2.resize(image_rgb, self.input_size)
        # Normalize (0-255 -> 0-1)
        normalized = resized.astype(np.float32) / 255.0
        # Change shape from (H, W, C) to (C, H, W)
        transposed = np.transpose(normalized, (2, 0, 1))
        # Add batch dimension: (1, C, H, W)
        input_tensor = np.expand_dims(transposed, axis=0)
        return input_tensor

    def postprocess(self, outputs):
        """
        Postprocess the ONNX model output to filter detections based on confidence threshold.
        
        :param outputs: Raw output from the model
        :return: List of filtered detections
        """
        # Remove the batch dimension: shape becomes (300, 6)
        detections = np.squeeze(outputs[0], axis=0)
        boxes = []

        for det in detections:
            # det is expected to be an array with 6 elements: [x1, y1, x2, y2, score, class_id]
            x1, y1, x2, y2, score, class_id = det

            if score >= self.conf_threshold:
                boxes.append([x1, y1, x2, y2, score, int(class_id)])

        return boxes

    def infer(self, frame: cv2.typing.MatLike):
        """
        Perform inference on a single frame.
        
        :param frame: The input frame (image) to process
        :return: List of detections with bounding boxes and class labels
        """
        input_tensor = self.preprocess(frame)
        outputs = self.session.run([self.output_name], {self.input_name: input_tensor})
        detections = self.postprocess(outputs)
        return detections

    def draw_detections(self, frame: cv2.typing.MatLike, detections: list):
        """
        Draw bounding boxes and labels on the frame.
        
        :param frame: The input frame (image) to draw on
        :param detections: List of detections to draw
        :return: Frame with drawn detections
        """
        for det in detections:
            x1, y1, x2, y2, score, class_id = det

            # Scale the bounding box back to the original image size
            h_orig, w_orig = frame.shape[:2]
            x_scale = w_orig / self.input_size[0]
            y_scale = h_orig / self.input_size[1]
            x1 = int(x1 * x_scale)
            y1 = int(y1 * y_scale)
            x2 = int(x2 * x_scale)
            y2 = int(y2 * y_scale)

            # Draw the bounding box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            label = f"{self.class_names[class_id]}: {score:.2f}"
            cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return frame

    def run(self):
        while True:
            try:
                frame = self.input_queue.get()
                
                # Perform inference
                detections = self.infer(frame)
                
                # Draw detections on the frame
                frame = self.draw_detections(frame, detections)

                self.output_queue.put(frame.copy())

            except KeyboardInterrupt:
                break
            except Exception as e:
                Log.exception(f"error at inference: {e}")
