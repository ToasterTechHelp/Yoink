"""CLI entry point: python -m yoink <file>"""

import argparse
import logging
import sys

from yoink.extractor import LayoutExtractor
from yoink.pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(
        prog="yoink",
        description="Yoink! — Extract components from lecture notes (PDF / images).",
    )
    parser.add_argument(
        "input_file",
        help="Path to a PDF or image file to extract components from.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default="./output",
        help="Directory to write the output JSON into (default: ./output).",
    )
    parser.add_argument(
        "--model-path",
        default=None,
        help="Path to YOLO .pt weights. If omitted, downloads from HuggingFace.",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=1024,
        help="YOLO prediction image size (default: 1024).",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.2,
        help="YOLO confidence threshold (default: 0.2).",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Device for inference, e.g. 'cpu' or 'cuda:0' (default: auto).",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="PDF rendering DPI (default: 200).",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        extractor = LayoutExtractor(
            model_path=args.model_path,
            imgsz=args.imgsz,
            conf=args.conf,
            device=args.device,
        )
        result = run_pipeline(
            input_file=args.input_file,
            output_dir=args.output_dir,
            extractor=extractor,
            dpi=args.dpi,
        )
        print(
            f"\nDone! Extracted {result['total_components']} components "
            f"from {result['total_pages']} page(s)."
        )
        print(f"Output: {args.output_dir}/{result['source_file'].rsplit('.', 1)[0]}_extracted.json")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logging.getLogger(__name__).error("Pipeline failed: %s", e, exc_info=True)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
