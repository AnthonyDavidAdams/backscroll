// BSOCR — Backscroll's on-device OCR helper.
//
// Reads an image file path from argv[1], runs Apple's Vision text recognizer
// (free, offline, no API keys), and prints the recognized text to stdout,
// one recognized line per output line. Compiled on first use by ocr.py:
//
//   swiftc -O -o bsocr BSOCR.swift
//
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1 else {
    FileHandle.standardError.write("usage: bsocr <image-path>\n".data(using: .utf8)!)
    exit(2)
}

let path = args[1]
guard let image = NSImage(contentsOfFile: path),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("could not load image: \(path)\n".data(using: .utf8)!)
    exit(3)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("vision error: \(error)\n".data(using: .utf8)!)
    exit(4)
}

var lines: [String] = []
if let results = request.results {
    for observation in results {
        if let candidate = observation.topCandidates(1).first {
            lines.append(candidate.string)
        }
    }
}
print(lines.joined(separator: "\n"))
