# Manual Generator

The Manual Generator provides a standalone interface for operators to trigger 3DPDF/2DPDF generation jobs manually — outside of the automated Innovator workflow.

## Use Cases

- Reprocessing a failed job without re-triggering the Innovator workflow
- Generating PDFs for items not yet registered in Innovator
- Testing and debugging the generation pipeline

## Responsibilities

- Accept manual input (item ID, CATIA file paths, output options)
- Submit job requests directly to the API server
- Display job progress and results to the operator

## Directory Structure

```
manual-generator/
├── README.md           ← this file
├── config.example.json ← configuration template
└── src/                ← source code
```

## Configuration

Copy `config.example.json` to `config.json` and fill in your environment values.

| Key | Description |
|-----|-------------|
| `api.baseUrl` | Base URL of the API server |
| `output.defaultPath` | Default local path for generated PDF files |
