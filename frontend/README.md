# NyayaSetu Frontend

A responsive Next.js web application for the NyayaSetu Multi-Agent Legal Assistance system. Built with Next.js App Router, TypeScript, and Tailwind CSS.

## Architecture Highlights

- **Runtime-Configurable Backend URL**: Does not use build-time `NEXT_PUBLIC_*` inlining. Instead, an App Router Route Handler (`app/api/config/route.ts`) dynamically resolves `process.env.BACKEND_URL` on each request, allowing backend URL changes without rebuilding.
- **Stage-Aware Orchestrator Interface**: Automatically transitions through `intake_question`, `final_check_gap`, and terminal `complete` stages.
- **Audited Citations & Visual Cues**: Accessible citation chips with distinct iconography and textual indicators for verified vs. rejected statutory sections.
- **Adversarial Debate & Safety Guardrails**: Displays contested grey-zone indications, judicial summaries, quality review adjustments, and statutory safety catch notifications.
- **Persistent Legal Disclaimer**: Non-dismissible notice in the global layout grounded in retrieved statutory text.

## Getting Started

### 1. Install Dependencies

```bash
npm install
```

### 2. Configure Environment

Copy the example environment file:

```bash
cp .env.local.example .env.local
```

Edit `.env.local` to specify your running FastAPI backend URL (defaults to `http://localhost:8000` for local development):

```env
BACKEND_URL=http://localhost:8000
```

### 3. Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### 4. Running Component Tests

Run the test suite with Vitest:

```bash
npm test
```

For watch mode:

```bash
npm run test:watch
```
