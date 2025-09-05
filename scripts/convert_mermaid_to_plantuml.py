#!/usr/bin/env python3
"""
Mermaid to PlantUML Converter for SCIRM Documentation

Converts Mermaid diagrams to PlantUML format for build-time SVG rendering.
Eliminates client-side JavaScript and CSP issues.

Usage:
    python scripts/convert_mermaid_to_plantuml.py

Author: Google Lead AI Architect · Google Senior SWE · Google Senior Lead Software Tester
"""

import os
import re
import glob
from pathlib import Path
from typing import List, Tuple, Dict

class MermaidToPlantUMLConverter:
    def __init__(self, docs_dir: str = "docs"):
        self.docs_dir = Path(docs_dir)
        self.converted_files = []
        self.todo_files = []
        
    def scan_markdown_files(self) -> List[Path]:
        """Scan for all markdown files in docs directory."""
        pattern = str(self.docs_dir / "**" / "*.md")
        return [Path(f) for f in glob.glob(pattern, recursive=True)]
    
    def extract_mermaid_blocks(self, content: str) -> List[Tuple[str, str]]:
        """Extract Mermaid code blocks and their content."""
        pattern = r'```mermaid\n(.*?)\n```'
        matches = re.findall(pattern, content, re.DOTALL)
        return [(match, match) for match in matches]
    
    def convert_flowchart(self, mermaid_content: str) -> str:
        """Convert Mermaid flowchart to PlantUML."""
        lines = mermaid_content.strip().split('\n')
        plantuml_lines = ['@startuml']
        
        # Detect direction
        first_line = lines[0].strip() if lines else ""
        if 'LR' in first_line or 'RL' in first_line:
            plantuml_lines.append('left to right direction')
        
        # Convert nodes and connections
        for line in lines:
            line = line.strip()
            if not line or line.startswith('graph') or line.startswith('flowchart'):
                continue
                
            # Handle subgraphs
            if line.startswith('subgraph'):
                subgraph_match = re.match(r'subgraph\s+"([^"]+)"', line)
                if subgraph_match:
                    plantuml_lines.append(f'package "{subgraph_match.group(1)}" {{')
                continue
            
            if line == 'end':
                plantuml_lines.append('}')
                continue
            
            # Handle style lines (convert to comments for now)
            if line.startswith('style '):
                style_match = re.match(r'style\s+(\w+)\s+fill:(#[0-9a-fA-F]{6})', line)
                if style_match:
                    node, color = style_match.groups()
                    plantuml_lines.append(f'note right of {node} : Color {color}')
                continue
            
            # Convert arrows and connections
            line = re.sub(r'-->', ' --> ', line)
            line = re.sub(r'--->', ' --> ', line)
            line = re.sub(r'-\.->', ' ..> ', line)
            
            # Handle node definitions with labels
            node_match = re.match(r'(\w+)\[([^\]]+)\]', line)
            if node_match:
                node_id, label = node_match.groups()
                # Clean label
                label = label.replace('<br/>', '\\n').replace('<br>', '\\n')
                plantuml_lines.append(f'rectangle "{label}" as {node_id}')
                continue
            
            # Handle simple connections
            if '-->' in line or '..>' in line:
                plantuml_lines.append(line)
        
        plantuml_lines.append('@enduml')
        return '\n'.join(plantuml_lines)
    
    def convert_sequence(self, mermaid_content: str) -> str:
        """Convert Mermaid sequence diagram to PlantUML."""
        lines = mermaid_content.strip().split('\n')
        plantuml_lines = ['@startuml']
        
        for line in lines:
            line = line.strip()
            if not line or line == 'sequenceDiagram':
                continue
            
            # Handle participant declarations
            if line.startswith('participant '):
                participant_match = re.match(r'participant\s+(\w+)(?:\s+as\s+"([^"]+)")?', line)
                if participant_match:
                    name = participant_match.group(1)
                    alias = participant_match.group(2) or name
                    plantuml_lines.append(f'participant "{alias}" as {name}')
                continue
            
            # Handle messages
            message_match = re.match(r'(\w+)\s*->>?\s*(\w+)\s*:\s*(.+)', line)
            if message_match:
                from_actor, to_actor, message = message_match.groups()
                plantuml_lines.append(f'{from_actor} -> {to_actor}: {message}')
                continue
            
            # Handle return messages
            return_match = re.match(r'(\w+)\s*-->>?\s*(\w+)\s*:\s*(.+)', line)
            if return_match:
                from_actor, to_actor, message = return_match.groups()
                plantuml_lines.append(f'{from_actor} --> {to_actor}: {message}')
                continue
        
        plantuml_lines.append('@enduml')
        return '\n'.join(plantuml_lines)
    
    def convert_gantt(self, mermaid_content: str) -> str:
        """Convert Mermaid Gantt to PlantUML (simplified as activity diagram)."""
        plantuml_lines = [
            '@startuml',
            '!theme plain',
            'title Gantt Chart (Converted from Mermaid)',
            '',
            '> **NOTE**: Complex Gantt chart conversion required.',
            '> Original Mermaid Gantt syntax needs manual PlantUML activity diagram conversion.',
            '> See PlantUML activity diagram documentation for proper syntax.',
            '',
            'start',
            ':TODO: Convert Gantt tasks to activity diagram;',
            'stop',
            '@enduml'
        ]
        return '\n'.join(plantuml_lines)
    
    def convert_mermaid_block(self, mermaid_content: str) -> Tuple[str, bool]:
        """Convert a single Mermaid block to PlantUML."""
        content = mermaid_content.strip()
        
        # Detect diagram type
        if content.startswith('graph ') or content.startswith('flowchart '):
            return self.convert_flowchart(content), False
        elif content.startswith('sequenceDiagram'):
            return self.convert_sequence(content), False
        elif content.startswith('gantt'):
            return self.convert_gantt(content), True
        elif content.startswith('classDiagram') or content.startswith('erDiagram'):
            # Complex diagrams - create TODO
            plantuml_lines = [
                '@startuml',
                '!theme plain',
                f'title {content.split()[0].title()} (Conversion Required)',
                '',
                '> **NOTE**: Complex diagram conversion required.',
                '> Original Mermaid syntax needs manual PlantUML conversion.',
                '',
                'rectangle "TODO: Convert to PlantUML" as TODO',
                '@enduml'
            ]
            return '\n'.join(plantuml_lines), True
        else:
            # Unknown diagram type
            plantuml_lines = [
                '@startuml',
                '!theme plain',
                'title Unknown Diagram Type (Conversion Required)',
                '',
                '> **NOTE**: Unknown Mermaid diagram type.',
                '> Manual conversion to PlantUML required.',
                '',
                'rectangle "TODO: Convert to PlantUML" as TODO',
                '@enduml'
            ]
            return '\n'.join(plantuml_lines), True
    
    def process_file(self, file_path: Path) -> bool:
        """Process a single markdown file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find all Mermaid blocks
            mermaid_blocks = self.extract_mermaid_blocks(content)
            if not mermaid_blocks:
                return False
            
            # Convert each block
            modified_content = content
            has_todos = False
            
            for original_block, mermaid_content in mermaid_blocks:
                plantuml_content, needs_todo = self.convert_mermaid_block(mermaid_content)
                
                # Replace the Mermaid block with PlantUML
                old_block = f'```mermaid\n{original_block}\n```'
                new_block = f'```plantuml\n{plantuml_content}\n```'
                
                if needs_todo:
                    # Add TODO admonition above the diagram
                    todo_note = '\n> **TODO**: This diagram requires manual conversion from Mermaid to PlantUML.\n> See the PlantUML documentation for proper syntax.\n\n'
                    new_block = todo_note + new_block
                    has_todos = True
                
                modified_content = modified_content.replace(old_block, new_block)
            
            # Write the modified content back
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
            
            self.converted_files.append(str(file_path))
            if has_todos:
                self.todo_files.append(str(file_path))
            
            return True
            
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            return False
    
    def run_conversion(self) -> Dict[str, List[str]]:
        """Run the conversion process on all markdown files."""
        markdown_files = self.scan_markdown_files()
        
        print(f"Found {len(markdown_files)} markdown files to process...")
        
        for file_path in markdown_files:
            if self.process_file(file_path):
                print(f"Converted: {file_path}")
        
        return {
            'converted': self.converted_files,
            'todos': self.todo_files
        }

def main():
    """Main conversion function."""
    print("🔄 Converting Mermaid diagrams to PlantUML...")
    print("=" * 60)
    
    converter = MermaidToPlantUMLConverter()
    results = converter.run_conversion()
    
    print("\n✅ Conversion Summary:")
    print(f"📄 Files converted: {len(results['converted'])}")
    print(f"⚠️  Files with TODOs: {len(results['todos'])}")
    
    if results['converted']:
        print("\n📋 Converted files:")
        for file_path in results['converted']:
            print(f"  - {file_path}")
    
    if results['todos']:
        print("\n⚠️  Files requiring manual conversion:")
        for file_path in results['todos']:
            print(f"  - {file_path}")
        print("\n💡 Search for '**TODO**' in these files for conversion notes.")
    
    print("\n🎯 Next steps:")
    print("1. Install plantuml_markdown: pip install plantuml-markdown")
    print("2. Ensure Java and Graphviz are installed")
    print("3. Run: python -m mkdocs build --strict")
    print("4. Review TODO items and complete manual conversions")

if __name__ == "__main__":
    main()
