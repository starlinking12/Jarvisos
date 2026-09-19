Jarvis OS

Jarvis OS is an early-stage, open-source desktop AI assistant built as a monorepo. It aims to provide a natural language interface for controlling desktop workflows, so users can tell their computer what to do instead of clicking through menus and switching between apps.

Current Status: Work in Progress (Pre-MVP). The project is under active development and is not yet feature complete.

The Problem Jarvis OS Solves

Modern desktop workflows are fragmented. Users constantly jump between apps, terminals, and browsers to complete simple tasks. Existing AI assistants are either locked inside a browser or require heavy setup. Jarvis OS fills this gap by offering a lightweight, always-available assistant that integrates with local system tools through a clean, extensible architecture.

Repository Structure

This project is organized as a monorepo using pnpm workspaces and Turborepo.

· apps - Runnable applications that make up the Jarvis OS experience.
· packages/contracts - Shared types and interface contracts used across the workspace.
· docs - Project documentation and design notes.
· turbo.json - Turborepo pipeline configuration.
· pnpm-workspace.yaml - Workspace package definitions.

Tech Stack

· Language: TypeScript
· Package Manager: pnpm
· Build System: Turborepo
· Planned AI Integration: Claude API for reasoning and command planning

Getting Started

1. Clone the repository:
   git clone https://github.com/starlinking12/Jarvisos.git
   cd Jarvisos
2. Install dependencies:
   pnpm install
3. Run the development pipeline:
   pnpm dev

Note: The project is not yet feature complete. Some apps and packages are scaffolds that will be filled in as development continues.

Roadmap

☑ Project initialization and monorepo setup
☑ Shared contracts package scaffolded
□ Core command parsing and intent handling
□ System integration module for file and app control
□ Claude API integration for complex reasoning
□ Desktop UI and system tray entry point
□ Public Beta Release

Contributing

This project is in active development. Feedback, bug reports, and feature requests are welcome. Please open an issue to discuss what you would like to see.

License

MIT License