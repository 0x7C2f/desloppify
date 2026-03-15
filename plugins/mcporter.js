import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const MCPORTER_BIN = process.env.MCPORTER_BIN ?? "/home/mrgrim/.npm-global/bin/mcporter";
const MCPORTER_CONFIG = process.env.MCPORTER_CONFIG ?? "/home/mrgrim/.mcporter/mcporter.json";

async function runMcporter(args) {
  try {
    const { stdout, stderr } = await execFileAsync(
      MCPORTER_BIN,
      ["--config", MCPORTER_CONFIG, ...args],
      { maxBuffer: 10 * 1024 * 1024 }
    );

    return [stdout, stderr].filter(Boolean).join("\n").trim();
  } catch (error) {
    const stdout = error.stdout ?? "";
    const stderr = error.stderr ?? "";
    throw new Error([error.message, stdout, stderr].filter(Boolean).join("\n").trim());
  }
}

export const McporterPlugin = async (ctx) => {
  const { client } = ctx;

  await client.app.log({
    body: {
      service: "mcporter-plugin",
      level: "info",
      message: `mcporter plugin loaded from desloppify using ${MCPORTER_CONFIG}`
    }
  });

  return {
    tool: {
      mcporter_list_servers: {
        description: "List configured mcporter MCP servers, optionally with tool schemas.",
        parameters: {
          type: "object",
          properties: {
            server: { type: "string" },
            schema: { type: "boolean" },
            json: { type: "boolean" },
            verbose: { type: "boolean" }
          }
        },
        execute: async (args) => {
          try {
            const command = ["list"];

            if (args.server) {
              command.push(args.server);
            }
            if (args.schema) {
              command.push("--schema");
            }
            if (args.json) {
              command.push("--json");
            }
            if (args.verbose) {
              command.push("--verbose");
            }

            return await runMcporter(command);
          } catch (error) {
            return `Error listing mcporter servers: ${error.message}`;
          }
        }
      },
      mcporter_call_tool: {
        description: "Call a configured mcporter tool by selector, optionally with JSON args.",
        parameters: {
          type: "object",
          properties: {
            selector: { type: "string" },
            args: { type: "object" },
            output: { type: "string", enum: ["text", "markdown", "json", "raw"] },
            timeout_ms: { type: "integer" }
          },
          required: ["selector"]
        },
        execute: async (args) => {
          try {
            const command = ["call", args.selector];

            if (args.args) {
              command.push("--args", JSON.stringify(args.args));
            }
            if (args.output) {
              command.push("--output", args.output);
            }
            if (args.timeout_ms) {
              command.push("--timeout", String(args.timeout_ms));
            }

            return await runMcporter(command);
          } catch (error) {
            return `Error calling mcporter tool: ${error.message}`;
          }
        }
      }
    }
  };
};

export default McporterPlugin;
