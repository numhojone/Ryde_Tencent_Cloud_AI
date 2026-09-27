# RydeResolve

**Tencent Cloud AI Singapore Hackathon 2026 — Digital Native Track (Ryde)**

## Overview

RydeResolve is a Multi-Agent Autonomous Dispute Resolution System for the Ryde
ride-hailing platform. When a dispute arises between a rider and a driver, the
system deploys specialised AI agents that investigate, advocate, and adjudicate
the case without human intervention.

### Agents

| Agent | Role |
|---|---|
| **Rider Advocate Agent** | Investigates the dispute from the rider's perspective, gathers relevant trip data, and builds the strongest case for the rider. |
| **Driver Advocate Agent** | Investigates the dispute from the driver's perspective, gathers relevant trip data, and builds the strongest case for the driver. |
| **Judge Agent** | Reviews arguments from both advocates, applies Ryde policies, and delivers a fair, transparent resolution. |

## Status

**Initial Development** — repository scaffolding has been set up. Agents, API,
LLM integration, tool logic, and frontend will be implemented incrementally.

## Directory Structure

```
.
├── app/
│   ├── agents/        # Agent implementations (Rider Advocate, Driver Advocate, Judge)
│   └── tools/         # Utility tools the agents can call (trip lookup, policy retrieval, etc.)
├── fixtures/
│   ├── disputes/      # Sample dispute records for testing
│   ├── trips/         # Sample trip data
│   ├── profiles/
│   │   ├── riders/    # Sample rider profiles
│   │   └── drivers/   # Sample driver profiles
│   └── policies/      # Ryde policies referenced by the Judge Agent
├── static/            # Static assets for the frontend
├── tests/             # Test suite
├── docs/              # Project documentation
├── .env.example       # Template for environment variables (populated incrementally)
└── .gitignore
```
