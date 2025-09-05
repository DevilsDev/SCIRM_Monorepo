#!/usr/bin/env python3
"""
SCIRM Documentation Visual Validator

Validates that all Markdown documentation files contain required visual elements:
- Tables (markdown tables)
- Mermaid diagrams 
- ASCII flows/arrows
- Charts and infographics

Supports both human-readable and JSON output for CI/CD integration.
"""

import os
import re
import json
import argparse
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ValidationResult:
    """Result of validating a single file."""
    file_path: str
    has_tables: bool
    has_mermaid: bool
    has_ascii_flow: bool
    has_charts: bool
    missing_elements: List[str]
    line_numbers: Dict[str, List[int]]
    is_valid: bool
    

@dataclass
class ValidationSummary:
    """Summary of all validation results."""
    total_files: int
    valid_files: int
    invalid_files: int
    files_missing_visuals: List[str]
    detailed_results: List[ValidationResult]
    

class VisualValidator:
    """Validates visual elements in Markdown documentation."""
    
    def __init__(self, docs_dir: str = "docs", output_format: str = "human"):
        self.docs_dir = Path(docs_dir)
        self.output_format = output_format
        
        # Patterns for detecting visual elements
        self.table_pattern = re.compile(r'^\s*\|.*\|.*\|', re.MULTILINE)
        self.mermaid_pattern = re.compile(r'```mermaid\s*\n.*?\n```', re.DOTALL)
        self.ascii_flow_pattern = re.compile(r'[→←↑↓⟶⟵⟷▶◀▲▼]|--+>|<--+|\|.*\||[┌┐└┘├┤┬┴┼]')
        self.chart_pattern = re.compile(r'!\[.*\]\(.*\.(png|jpg|jpeg|svg|gif)\)|```chart|```plotly|```d3')
        
        # Files to exclude from validation
        self.excluded_patterns = [
            r'.*\.git.*',
            r'.*node_modules.*',
            r'.*\.venv.*',
            r'.*__pycache__.*',
            r'.*\.pytest_cache.*',
            r'.*site/.*',
            r'.*README\.md$',  # Top-level README often doesn't need visuals
            r'.*CHANGELOG\.md$',
            r'.*LICENSE\.md$',
        ]
        
        # Required visual elements per file type
        self.requirements = {
            'architecture': ['tables', 'mermaid'],
            'security': ['tables', 'mermaid'],
            'observability': ['tables', 'mermaid'],
            'roadmap': ['tables', 'mermaid'],
            'product': ['tables', 'mermaid'],
            'default': ['tables']  # At minimum, require tables
        }

    def should_exclude_file(self, file_path: Path) -> bool:
        """Check if file should be excluded from validation."""
        file_str = str(file_path)
        for pattern in self.excluded_patterns:
            if re.match(pattern, file_str):
                return True
        return False

    def get_file_requirements(self, file_path: Path) -> List[str]:
        """Get required visual elements for a file based on its path."""
        file_str = str(file_path).lower()
        
        for category in self.requirements:
            if category != 'default' and category in file_str:
                return self.requirements[category]
        
        return self.requirements['default']

    def find_pattern_lines(self, content: str, pattern: re.Pattern) -> List[int]:
        """Find line numbers where pattern matches."""
        lines = content.split('\n')
        line_numbers = []
        
        for i, line in enumerate(lines, 1):
            if pattern.search(line):
                line_numbers.append(i)
        
        return line_numbers

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate visual elements in a single Markdown file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            print("Running visual validation...")
            return ValidationResult(
                file_path=str(file_path),
                has_tables=False,
                has_mermaid=False,
                has_ascii_flow=False,
                has_charts=False,
                missing_elements=['error_reading_file'],
                line_numbers={},
                is_valid=False
            )

        # Check for visual elements
        has_tables = bool(self.table_pattern.search(content))
        has_mermaid = bool(self.mermaid_pattern.search(content))
        has_ascii_flow = bool(self.ascii_flow_pattern.search(content))
        has_charts = bool(self.chart_pattern.search(content))

        # Find line numbers for each element type
        line_numbers = {
            'tables': self.find_pattern_lines(content, self.table_pattern),
            'mermaid': self.find_pattern_lines(content, self.mermaid_pattern),
            'ascii_flow': self.find_pattern_lines(content, self.ascii_flow_pattern),
            'charts': self.find_pattern_lines(content, self.chart_pattern)
        }

        # Determine required elements for this file
        required_elements = self.get_file_requirements(file_path)
        
        # Check what's missing
        missing_elements = []
        element_status = {
            'tables': has_tables,
            'mermaid': has_mermaid,
            'ascii_flow': has_ascii_flow,
            'charts': has_charts
        }

        for element in required_elements:
            if not element_status.get(element, False):
                missing_elements.append(element)

        # File is valid if no required elements are missing
        is_valid = len(missing_elements) == 0

        return ValidationResult(
            file_path=str(file_path),
            has_tables=has_tables,
            has_mermaid=has_mermaid,
            has_ascii_flow=has_ascii_flow,
            has_charts=has_charts,
            missing_elements=missing_elements,
            line_numbers=line_numbers,
            is_valid=is_valid
        )

    def find_markdown_files(self) -> List[Path]:
        """Find all Markdown files in the docs directory."""
        markdown_files = []
        
        for file_path in self.docs_dir.rglob("*.md"):
            if not self.should_exclude_file(file_path):
                markdown_files.append(file_path)
        
        return sorted(markdown_files)

    def validate_all(self) -> ValidationSummary:
        """Validate all Markdown files in the docs directory."""
        markdown_files = self.find_markdown_files()
        results = []
        
        for file_path in markdown_files:
            result = self.validate_file(file_path)
            results.append(result)
        
        # Calculate summary statistics
        valid_files = sum(1 for r in results if r.is_valid)
        invalid_files = len(results) - valid_files
        files_missing_visuals = [r.file_path for r in results if not r.is_valid]
        
        return ValidationSummary(
            total_files=len(results),
            valid_files=valid_files,
            invalid_files=invalid_files,
            files_missing_visuals=files_missing_visuals,
            detailed_results=results
        )

    def format_human_output(self, summary: ValidationSummary) -> str:
        """Format validation results for human reading."""
        output = []
        
        # Header
        output.append("=" * 60)
        output.append("SCIRM Documentation Visual Validation Report")
        output.append("=" * 60)
        output.append("")
        
        # Summary
        output.append("📊 SUMMARY")
        output.append(f"Total files checked: {summary.total_files}")
        output.append(f"✅ Valid files: {summary.valid_files}")
        output.append(f"❌ Files missing visuals: {summary.invalid_files}")
        output.append("")
        
        if summary.invalid_files == 0:
            output.append("🎉 All documentation files contain required visual elements!")
            output.append("")
        else:
            output.append("📋 FILES MISSING VISUAL ELEMENTS:")
            output.append("")
            
            for result in summary.detailed_results:
                if not result.is_valid:
                    output.append(f"❌ {result.file_path}")
                    output.append(f"   Missing: {', '.join(result.missing_elements)}")
                    
                    # Show what was found
                    found_elements = []
                    if result.has_tables:
                        found_elements.append("tables")
                    if result.has_mermaid:
                        found_elements.append("mermaid")
                    if result.has_ascii_flow:
                        found_elements.append("ascii_flow")
                    if result.has_charts:
                        found_elements.append("charts")
                    
                    if found_elements:
                        output.append(f"   Found: {', '.join(found_elements)}")
                    else:
                        output.append("   Found: none")
                    output.append("")
            
            output.append("💡 RECOMMENDATIONS:")
            output.append("- Add tables to show structured data and comparisons")
            output.append("- Include Mermaid diagrams for architecture and flows")
            output.append("- Use ASCII arrows (→, ←, ↑, ↓) for simple flows")
            output.append("- Consider charts/infographics for complex data")
            output.append("")
            output.append("📖 Style Guide: docs/development/doc-style.md")
        
        return "\n".join(output)

    def format_json_output(self, summary: ValidationSummary) -> str:
        """Format validation results as JSON for CI/CD integration."""
        # Convert dataclasses to dictionaries
        json_data = {
            'summary': {
                'total_files': summary.total_files,
                'valid_files': summary.valid_files,
                'invalid_files': summary.invalid_files,
                'files_missing_visuals': summary.files_missing_visuals
            },
            'results': [asdict(result) for result in summary.detailed_results]
        }
        
        return json.dumps(json_data, indent=2)

    def run_validation(self) -> Tuple[ValidationSummary, str]:
        """Run validation and return results with formatted output."""
        summary = self.validate_all()
        
        if self.output_format == 'json':
            output = self.format_json_output(summary)
        else:
            output = self.format_human_output(summary)
        
        return summary, output


def main():
    """Main entry point for the visual validator."""
    parser = argparse.ArgumentParser(
        description="Validate visual elements in SCIRM documentation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python validate_visuals.py                    # Human-readable output
  python validate_visuals.py --format json     # JSON output for CI/CD
  python validate_visuals.py --docs-dir docs   # Custom docs directory
        """
    )
    
    parser.add_argument(
        '--docs-dir',
        default='docs',
        help='Directory containing documentation files (default: docs)'
    )
    
    parser.add_argument(
        '--format',
        choices=['human', 'json'],
        default='human',
        help='Output format (default: human)'
    )
    
    parser.add_argument(
        '--fail-on-missing',
        action='store_true',
        help='Exit with non-zero code if any files are missing visuals'
    )
    
    args = parser.parse_args()
    
    # Validate that docs directory exists
    if not os.path.exists(args.docs_dir):
        print(f"Error: Documentation directory '{args.docs_dir}' does not exist", file=sys.stderr)
        sys.exit(1)
    
    # Run validation
    validator = VisualValidator(docs_dir=args.docs_dir, output_format=args.format)
    summary, output = validator.run_validation()
    
    # Print results
    print(output)
    
    # Exit with appropriate code
    if args.fail_on_missing and summary.invalid_files > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
