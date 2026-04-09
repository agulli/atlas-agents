# Atlas Agents: Building AI Agents

Welcome to the official code repository for **"Building AI Agents: A Hands-On Perspective"**. 

This repository provides a step-by-step journey from building raw ReAct loops to orchestrating complex multi-agent production systems. Instead of focusing on a single library, we explore patterns across the most popular frameworks, including LangGraph, CrewAI, and the OpenAI Agents SDK.

## 🚀 Getting Started

### 1. Clone the repository
\`\`\`bash
git clone https://github.com/agulli/atlas-agents.git
cd atlas-agents
\`\`\`

### 2. Set up your environment
Create a \`.env\` file from the example:
\`\`\`bash
cp .env.example .env
\`\`\`
Fill in your API keys:
- \`OPENAI_API_KEY\`
- \`ANTHROPIC_API_KEY\`
- \`GOOGLE_API_KEY\`

### 3. Install dependencies
\`\`\`bash
pip install -r requirements.txt
\`\`\`

## 📂 Repository Structure

| Chapter | Title | Focus |
| :--- | :--- | :--- |
| **Ch 01** | [ReAct from Scratch](./ch01_react_from_scratch) | Implementing the "Reason + Act" loop without any framework. |
| **Shared** | [Shared Utility Library](./shared) | Reusable tool-calling logic and 30+ declarative skills. |

## 🛠️ The Atlas Architecture

The agents in this book follow the **Atlas Architecture**:
- **Baseline**: Raw implementations to understand the "math" of the loop.
- **Frameworks**: Implementations using LangGraph, CrewAI, and Swarm.
- **Online Extras**: Advanced patterns for streaming, memory decay, and guardrails.

## 📖 About the Book

"Building AI Agents" takes a pattern-first approach to agentic AI. You’ll learn how to build agents that are:
- **Stateful**: Managing complex conversations with LangGraph.
- **Collaborative**: Orchestrating crews with CrewAI.
- **Secure**: Implementing guardrails and sandboxed code execution with E2B.
- **Portable**: Benchmarking and switching between GPT-4o, Claude 3.5, and Gemini 2.0.

---
© 2026 Antonio Gulli | Part of the Atlas Agentic Series
