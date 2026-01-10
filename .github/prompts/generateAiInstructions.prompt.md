---
name: generateAiInstructions
description: Generates project-specific instructions to guide AI coding agents.
argument-hint: Focus areas (architecture, workflows, conventions)
---
Analyze the current workspace to generate or update a comprehensive set of instructions for AI coding agents (e.g., `.github/copilot-instructions.md`, `.cursorrules`).

Focus on capturing the essential "tacit knowledge" of the project:
1.  **Architecture & Big Picture**: Major components, service boundaries, data flow strategies, and key design decisions.
2.  **Critical Workflows**: How to build, run, and debug the application. Include specific commands that might not be obvious.
3.  **Project Conventions**: Coding patterns, preferred libraries, folder structure, and specific "do's and don'ts" for this codebase.
4.  **Integration Points**: How different parts of the system communicate (APIs, databases, events).

Review existing documentation (README, existing rules files) if available to merge valuable context.

Produce the output in a clear, structured Markdown format ready to be saved as the project's AI instruction file.
