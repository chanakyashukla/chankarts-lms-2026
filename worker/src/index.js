/**
 * ChankArts LMS 2026 — production Worker.
 *
 * Serves the existing static frontend (Workers Static Assets) and forwards
 * API traffic to the existing FastAPI application running in a Cloudflare
 * Container (the repository's root Dockerfile, unmodified).
 *
 * One named container instance = one authoritative application state:
 * every authorized user reads and writes the same persistent database
 * (Neon PostgreSQL via DATABASE_URL), regardless of device or location.
 */
import { DurableObject } from "cloudflare:workers";

// Single instance: one authoritative app + shared DB. (Scale-out is possible
// later; state lives in PostgreSQL, not the container.)
const INSTANCE_NAME = "main";
// Short idle-sleep so an academy's bursty usage still scales to ~zero cost.
const INACTIVITY_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
const CONTAINER_PORT = 8000;
const READY_ATTEMPTS = 150; // ~30s worst case for cold start + migrations

export class LmsBackend extends DurableObject {
    starting;

    constructor(ctx, env) {
        super(ctx, env);
        const container = ctx.container;
        if (container.running) {
            void ctx.blockConcurrencyWhile(() =>
                container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS),
            );
        }
    }

    async fetch(request) {
        // Concurrent requests share one startup + readiness check.
        this.starting ??= this.startAndWaitForPort().finally(() => {
            this.starting = undefined;
        });
        await this.starting;

        const url = new URL(request.url);
        url.protocol = "http:";
        url.host = "container";
        const forwarded = new Request(url, request);
        forwarded.headers.delete("host");
        return this.ctx.container.getTcpPort(CONTAINER_PORT).fetch(forwarded);
    }

    async startAndWaitForPort() {
        const container = this.ctx.container;
        if (!container.running) {
            container.start({
                image: container.images.base,
                instance: "lite", // 256 MiB / 1/16 vCPU — validated against the app's idle footprint
                enableInternet: true, // required for Neon PostgreSQL + R2
                env: this.containerEnv(),
            });
        }
        await container.setInactivityTimeout(INACTIVITY_TIMEOUT_MS);

        const port = container.getTcpPort(CONTAINER_PORT);
        let lastError;
        for (let attempt = 0; attempt < READY_ATTEMPTS; attempt++) {
            try {
                const response = await port.fetch("http://container/health", {
                    signal: AbortSignal.timeout(1000),
                });
                await response.body?.cancel();
                if (!response.ok) {
                    throw new Error(`Health check returned ${response.status}`);
                }
                return;
            } catch (error) {
                lastError = error;
                await scheduler.wait(200);
            }
        }
        throw new Error("Container did not become ready on port 8000", {
            cause: lastError,
        });
    }

    // Forward production configuration into the container. Secrets are set
    // with `npx wrangler secret put ...` and are never committed anywhere.
    containerEnv() {
        const pick = (name) => (this.env[name] !== undefined ? String(this.env[name]) : undefined);
        const env = {};
        const keys = [
            // database (Neon PostgreSQL)
            "DATABASE_URL",
            // auth
            "SECRET_KEY", "ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES",
            // first-boot administrator seeding (change immediately after go-live)
            "SEED_ADMIN_EMAIL", "SEED_ADMIN_USERNAME", "SEED_ADMIN_PASSWORD",
            "SEED_ADMIN_FIRST_NAME", "SEED_ADMIN_LAST_NAME",
            // application
            "APP_NAME", "APP_VERSION", "DEBUG", "FRONTEND_URL", "ALLOWED_ORIGINS",
            "TIMEZONE", "CURRENCY",
            // uploads: durable R2 storage (FUSE mount; see docker-entrypoint.sh)
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "R2_BUCKET_NAME", "R2_ACCOUNT_ID",
            // optional integrations
            "WEB3FORMS_ACCESS_KEY", "EMAIL_TEST_MODE", "ADMIN_EMAIL", "FROM_NAME",
            "RAZORPAY_MODE", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET",
            "RAZORPAY_WEBHOOK_SECRET", "RAZORPAY_CURRENCY",
            "UPLOAD_DIR", "MAX_UPLOAD_MB",
            "RATE_LIMIT_ENABLED", "AUTH_RATE_LIMIT_ATTEMPTS",
            "AUTH_RATE_LIMIT_WINDOW_SECONDS",
        ];
        for (const key of keys) {
            const value = pick(key);
            if (value !== undefined) env[key] = value;
        }
        return env;
    }
}

export default {
    async fetch(request, env) {
        const pathname = new URL(request.url).pathname;
        const isApi =
            pathname === "/api" ||
            pathname.startsWith("/api/") ||
            pathname === "/health" ||
            pathname === "/docs" ||
            pathname.startsWith("/docs/") ||
            pathname === "/redoc" ||
            pathname === "/openapi.json";
        if (isApi) {
            return env.LMS_BACKEND.getByName(INSTANCE_NAME).fetch(request);
        }
        return env.ASSETS.fetch(request);
    },
};
