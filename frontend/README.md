# RootLens dashboard

React 19, Vite and Tailwind 4 front end for the RootLens API. Every screen reads live data from the FastAPI backend; nothing is mocked.

## Run

```bash
npm install
cp .env.example .env     # optional: sets VITE_API_URL (default http://127.0.0.1:8000)
npm run dev              # http://localhost:5173
npm run build
npm test
```

Start the API first (`make api` in the backend repo). The API address can also be changed in Settings > Data.

## Screens and endpoints

| Screen | Endpoints |
|--------|-----------|
| Overview | `/api/overview`, `/api/metrics`, `/api/ranking`, `/api/runs` |
| Ranking | `/api/ranking`, `/api/safe-windows` |
| Safe windows | `/api/safe-windows` |
| Savings | `/api/savings/default`, `POST /api/savings`, `/api/safe-windows` |
| Captures | `/api/runs`, `/api/runs/{index}` |
| Summary panel | `/api/overview`, `/api/runs` |
| Navbar | `/api/health`, `/api/overview` |

A 503 from the API means the artifact has not been generated yet; the screen says so and offers a retry.
