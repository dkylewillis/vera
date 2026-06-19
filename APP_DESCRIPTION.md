# VERA App Overview

## What This App Is

This application is a grounded document assistant built around the `.vera` format.  
It helps users search long source documents, get useful answers, and verify those answers against the original pages.

In short: it turns document Q&A into a transparent, source-backed workflow.

## Who It Is For

- Teams working with large manuals, policies, standards, or reports
- Analysts and compliance users who need citation-ready answers
- Engineers and operators who need fast lookup in technical documents
- AI-assisted workflows that require grounded, auditable outputs

## Core Value

- Better search over long documents
- Answers tied back to source pages and sections
- Fewer hallucinated responses through grounding and citation
- One reusable `.vera` file that works across tools and sessions

## Key Capabilities

### 1. Source Document Viewer
- View original document pages
- Navigate by page and section
- Jump from answer citations directly to source location
- Work in a two-pane layout with Ask on the left and Source Document on the right
- Open documents from the native File menu and show file metrics in the bottom status bar
- Expand the Source Document pane when reviewing grounded PDF highlights

### 2. Prompt Input + Retrieval
- Accept natural language user prompts
- Retrieve relevant chunks from `.vera` using keyword, semantic, or hybrid search
- Pass retrieved context into response generation

### 3. Visual Grounding
- Highlight retrieved passages in the source view
- Show where each claim came from (page and heading path)
- Keep selected citations focused on the source PDF, with metadata and retrieval details available on demand

### 4. Session Management
- Save conversations and retrieval state
- Revisit prior prompts, results, and citations
- Support iterative research and comparison across runs

### 5. Configurable Instructions
- Layered instructions for response behavior
- Configurable augmentation that combines system/app instructions, retrieved context, and user prompt
- Optional domain-specific response templates

### 6. LLM Integrations
- Connect to one or more LLM providers
- Select model by task profile (speed, quality, cost)
- Stream responses and preserve grounded citation links

### 7. External Tool Connectivity
- Integrate useful supporting tools (search, APIs, data sources, utilities)
- Use tool outputs as additional context
- Keep provenance so users can see what informed the answer

## How It Works (High Level)

1. User asks a question
2. App retrieves relevant context from `.vera`
3. App composes prompt with instructions + context + user input
4. App returns a grounded cited draft, or passes the composed prompt to a configured LLM provider
5. Citation clicks open the Source Document viewer and highlight the supporting region

## Why `.vera` Matters in This App

A `.vera` file is a portable retrieval archive that packages:

- source document content
- structured text blocks and chunks
- keyword index
- embeddings
- citation metadata
- visual grounding regions

This lets the app deliver faster, more consistent, and more explainable answers than querying raw PDFs alone.

## Design Principles

- Grounded first: answers should be traceable to sources
- Transparent by default: show evidence and retrieval path
- Configurable behavior: adapt to team and domain needs
- Tool-agnostic architecture: integrate models and utilities safely
- Reproducible sessions: preserve context and configuration history

## Example Use Cases

- Compliance question answering with page-level citations
- Technical operations lookup in large manuals
- Policy interpretation with source traceability
- Analyst research workflows with persistent sessions

## Success Criteria

- Users can find relevant answers quickly
- Answers include clear evidence paths
- Teams trust outputs because sources are visible
- Configuration and session history support repeatable workflows

## Future Enhancements

- Advanced reranking and confidence scoring
- Multi-document `.vera` collections
- Evaluation dashboard for groundedness and retrieval quality
- Role-based governance and audit trails
- Stronger tool orchestration and approval policies
