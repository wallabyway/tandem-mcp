import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");

  return {
    server: {
      port: 3000,
      open: true,
    },
    plugins: [
      {
        name: "tandem-token-api",
        configureServer(server) {
          const clientId = env.TANDEM_CLIENT_ID;
          const clientSecret = env.TANDEM_CLIENT_SECRET;

          let cached = null;

          server.middlewares.use("/api/token", async (_req, res) => {
            try {
              if (cached && cached.expiresAt > Date.now()) {
                res.setHeader("Content-Type", "application/json");
                res.end(JSON.stringify({ access_token: cached.token }));
                return;
              }

              const params = new URLSearchParams({
                grant_type: "client_credentials",
                scope: "data:read data:write",
              });

              const resp = await fetch(
                "https://developer.api.autodesk.com/authentication/v2/token",
                {
                  method: "POST",
                  headers: {
                    "Content-Type": "application/x-www-form-urlencoded",
                    Authorization:
                      "Basic " +
                      Buffer.from(`${clientId}:${clientSecret}`).toString(
                        "base64"
                      ),
                  },
                  body: params.toString(),
                }
              );

              if (!resp.ok) {
                const text = await resp.text();
                res.statusCode = resp.status;
                res.end(text);
                return;
              }

              const data = await resp.json();
              cached = {
                token: data.access_token,
                expiresAt: Date.now() + (data.expires_in - 60) * 1000,
              };

              res.setHeader("Content-Type", "application/json");
              res.end(JSON.stringify({ access_token: data.access_token }));
            } catch (err) {
              res.statusCode = 500;
              res.end(JSON.stringify({ error: err.message }));
            }
          });
        },
      },
    ],
  };
});
