# Devanagari

An [Omarchy](https://omarchy.org) bar plugin that reads Nepali and other Devanagari from a screen region, an image, or a PDF. The reading happens on this computer.

The panel leads with a machine check: free memory, the CPU, and which engine is allowed. Tesseract is the reader. A small quantized model can be downloaded from Hugging Face when the check says the file fits. It is not loaded for reading on a machine without an ONNX runtime, and this plugin does not install one. An in-house model trained on local Nepal pages is listed and has no file yet. When it is published, the same check decides the download.

Use it for free. If it helps, pay what you are comfortable with, including nothing. Nothing is locked behind a payment.

## Install

```sh
omarchy plugin add https://github.com/ashiskharel/omarchy-devanagari.git --enable --yes
```

That puts `अ` on the right side of the bar. Move it with:

```sh
omarchy bar put ashis.devanagari --section right
```

The terminal command is optional. After install, link it once:

```sh
mkdir -p ~/.local/bin
ln -sfn ~/.config/omarchy/plugins/ashis.devanagari/bin/devanagari ~/.local/bin/devanagari
```

Omarchy already provides Tesseract, `grim`, `slurp`, and `hyprpicker`. No sudo, and no PyTorch.

## Remove

```sh
omarchy plugin remove ashis.devanagari
```

That disables the plugin and deletes the installed copy. Downloaded Nepali data stays in `~/.local/share/omarchy-devanagari/`. Readings stay in `~/.cache/omarchy-devanagari/`.

## Machine check

```sh
devanagari hardware
```

Tesseract's Nepali data is about 2 MB. Fetch needs 64 MB free.

The optional model is PP-OCRv5 Devanagari recognition weights, Apache-2.0, pinned from Hugging Face at `xberg-io/paddleocr-onnx-models` revision `bc5ec866cf0e798e667808dfa51b0ba8ad0dafc8`. A download is allowed when free memory covers twice the file size plus 512 MB. `--force` can pass that memory line. The checksum and the byte cap still apply. Loading it for reading would also require an ONNX runtime that is already installed, and a trial load that leaves at least 400 MB free. This plugin never installs that runtime, and page reading stays on Tesseract.

```sh
devanagari fetch
devanagari fetch --model ppocr-devanagari
devanagari models
```

`ashis-nepali` is the slot for a later in-house model. `devanagari fetch --model ashis-nepali` refuses, because there is no file.

## Read

```sh
devanagari capture
devanagari read page.png
devanagari read notice.pdf
devanagari eval
```

`capture` copies the region to the clipboard. A PDF uses its text layer when it has one, then OCR. `eval` prints the character error rate of the pages in `samples/`.

A support link is optional. Put an `https` URL in `~/.config/omarchy-devanagari/config.json`:

```json
{ "supportUrl": "https://example.com/pay-what-you-are-comfortable-with" }
```

The panel opens that URL. The reader works the same when the field is empty.

## This laptop

`devanagari hardware` on the Lenovo this was written on, after the Nepali data was fetched:

```
1543 MB free of 3338 MB. Reading with Tesseract Nepali. The optional Devanagari model can be downloaded and will not be loaded for reading.

CPU     Intel(R) Core(TM) i3-6100U CPU @ 2.30GHz (4 threads)
Memory  1543 MB free of 3338 MB
GPU     HD Graphics 520
Reader  tesseract 5.5.3

Engines
  Tesseract Nepali: Installed. This is the reader.
  PP-OCRv5 Devanagari: 1543 MB free covers the 528 MB check. Download stores the weights. Reading stays on Tesseract: ONNX runtime is not installed, and this plugin does not install it.
  In-house Nepal print: Not published. When a model trained on local Nepal pages is on Hugging Face, it becomes a card like the others, and the same machine check decides the download.
```

The three sample pages score a character error rate of 0.000 with Tesseract. That is clean print rendered from Noto Sans Devanagari, not a photograph of a notice.
