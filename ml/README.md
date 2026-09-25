# Improving Nepali OCR

The number that matters is `devanagari eval`. It scores the pictures in `samples/` against the text files beside them and prints a character error rate.

Add a page by putting a small image and a `.txt` file with the same name in `samples/`. Print first: a notice, a textbook page you have the right to keep, a shop sign you photographed. Handwriting can wait. Large scans stay out of git.

This laptop does not train. It has no NVIDIA GPU and too little memory for a training run. A later hosted GPU can fine-tune a small recognizer, export an int8 ONNX file, and publish it on Hugging Face with a model card that names the pages and the license.

That published file becomes another entry in `devanagari/cards.json`, same shape as `ppocr-devanagari`. The machine check then decides whether this computer downloads it. Weights never go in git.

Until that model exists, `ashis-nepali` is listed and has no URL.
