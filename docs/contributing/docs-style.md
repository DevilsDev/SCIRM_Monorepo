# Documentation Style Guide

This guide ensures consistency and quality across all SCIRM documentation.

## Writing Style

### Voice and Tone
- **Active Voice**: Use active voice whenever possible
- **Present Tense**: Write in present tense for current features
- **Direct Language**: Be clear and concise
- **Professional Tone**: Maintain professional but approachable tone

### Language Guidelines
- Use American English spelling
- Avoid jargon and acronyms without explanation
- Write for your audience (technical vs. business users)
- Use inclusive language

## Content Structure

### Page Organization
```markdown
# Page Title (H1 - only one per page)

Brief introduction paragraph.

## Major Section (H2)

Content for major sections.

### Subsection (H3)

Detailed content and examples.

#### Minor Section (H4)

Use sparingly for complex topics.
```

### Required Elements
- **H1 Title**: Clear, descriptive page title
- **Introduction**: Brief overview of page content
- **Logical Flow**: Information organized from general to specific
- **Examples**: Code snippets and practical examples where relevant

## Formatting Standards

### Code Blocks
```python
# Use language-specific syntax highlighting
def example_function():
    return "Hello, SCIRM!"
```

### Links
- **Internal Links**: Use relative paths `[link text](../other-page.md)`
- **External Links**: Include full URLs `[link text](https://example.com)`
- **Descriptive Text**: Link text should describe the destination

### Lists
- Use bullet points for unordered lists
- Use numbers for sequential steps
- Keep list items parallel in structure
- Use consistent punctuation

### Tables
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data     | Data     | Data     |

### Admonitions
```markdown
!!! note
    Use admonitions for important information.

!!! warning
    Use warnings for critical information.

!!! tip
    Use tips for helpful suggestions.
```

## Technical Content

### API Documentation
- Include request/response examples
- Document all parameters
- Show error responses
- Provide working code samples

### Configuration Examples
- Use realistic values
- Include comments explaining options
- Show both minimal and complete configurations
- Highlight security considerations

## Images and Media

### Image Guidelines
- Store images in `/docs/assets/`
- Use descriptive filenames
- Optimize for web (< 500KB)
- Include alt text for accessibility

### Diagrams
- Use Mermaid for technical diagrams
- Keep diagrams simple and readable
- Include text descriptions for complex diagrams

## Review Process

### Self-Review Checklist
- [ ] Spelling and grammar checked
- [ ] Links tested and working
- [ ] Code examples tested
- [ ] Images display correctly
- [ ] Follows style guidelines

### Peer Review
- Technical accuracy verification
- Clarity and readability assessment
- Style guide compliance check
- Accessibility review
