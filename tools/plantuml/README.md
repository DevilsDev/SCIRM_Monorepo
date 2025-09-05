# PlantUML Toolchain for SCIRM Documentation

This directory contains the PlantUML JAR file and configuration for build-time diagram rendering.

## Version Information

- **PlantUML Version**: 1.2024.0
- **JAR File**: `plantuml.jar`
- **Format**: SVG (build-time rendering)
- **Security**: No client-side JavaScript required

## Local Preview

To preview PlantUML diagrams locally:

```bash
# Generate SVG from .puml file
java -jar tools/plantuml/plantuml.jar -tsvg diagram.puml

# Generate PNG from .puml file  
java -jar tools/plantuml/plantuml.jar -tpng diagram.puml
```

## Requirements

- **Java**: OpenJDK 11+ or 17 (recommended)
- **Graphviz**: Required for complex layouts
- **PlantUML JAR**: Included in this directory

## CI/CD Integration

The CI pipeline automatically:
1. Installs Java and Graphviz
2. Uses the vendored PlantUML JAR
3. Sets `PLANTUML_JAR` environment variable
4. Renders diagrams during MkDocs build

## Configuration

PlantUML is configured in `mkdocs.yml`:

```yaml
markdown_extensions:
  - plantuml_markdown:
      server: null
      format: svg
      cachedir: .plantuml-cache
      theme: default
      jar_path: tools/plantuml/plantuml.jar
```

## Security Benefits

- **Build-time rendering**: Diagrams are SVG files, no runtime JavaScript
- **CSP compliant**: No external dependencies or inline scripts
- **Performance**: Static SVG files load faster than client-side rendering
- **Offline capable**: No CDN dependencies
