import { readdir, access } from "node:fs/promises";
import path from "node:path";

const SKILLNET_API = process.env.SKILLNET_API ?? "http://api-skillnet.openkg.cn/v1/search";
const LOCAL_SKILLS_DIR = process.env.SKILLNET_SKILLS_DIR ?? path.resolve(process.cwd(), ".desloppify", "skills");

async function searchSkillNet(params) {
  const url = new URL(SKILLNET_API);

  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  const response = await fetch(url.toString());

  if (!response.ok) {
    throw new Error(`SkillNet API error ${response.status}: ${await response.text()}`);
  }

  const json = await response.json();

  if (!json.success) {
    throw new Error(`SkillNet returned success=false for query: ${params.q}`);
  }

  return json;
}

function formatRemoteSkills(skills, meta) {
  if (!skills || skills.length === 0) {
    return `No SkillNet results for "${meta.query}".`;
  }

  const lines = [
    "## SkillNet Results",
    `Query: **${meta.query}** | Mode: ${meta.mode} | Total: ${meta.total ?? "?"}`,
    ""
  ];

  for (const skill of skills) {
    lines.push(`### ${skill.skill_name}`);
    lines.push(`- Description: ${skill.skill_description}`);
    lines.push(`- Author: ${skill.author}`);
    lines.push(`- Category: ${skill.category ?? "-"}`);
    lines.push(`- Stars: ${skill.stars ?? 0}`);

    if (skill.skill_url) {
      lines.push(`- URL: ${skill.skill_url}`);
    }

    lines.push("");
  }

  return lines.join("\n");
}

async function formatLocalSkills() {
  const entries = await readdir(LOCAL_SKILLS_DIR, { withFileTypes: true });
  const skills = [];

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const skillFile = path.join(LOCAL_SKILLS_DIR, entry.name, "SKILL.md");

    try {
      await access(skillFile);
      skills.push(entry.name);
    } catch {
      continue;
    }
  }

  skills.sort();

  const lines = [
    `## Local SkillNet Skills`,
    `Path: \`${LOCAL_SKILLS_DIR}\``,
    `Count: ${skills.length}`,
    ""
  ];

  for (const name of skills) {
    lines.push(`- ${name}`);
  }

  return lines.join("\n");
}

export const SkillNetPlugin = async (ctx) => {
  const { client } = ctx;

  await client.app.log({
    body: {
      service: "skillnet-plugin",
      level: "info",
      message: `SkillNet plugin loaded from desloppify using ${LOCAL_SKILLS_DIR}`
    }
  });

  return {
    tool: {
      skillnet_local_skills: {
        description: "List locally installed skills from the shared SkillNet skills directory.",
        parameters: {
          type: "object",
          properties: {}
        },
        execute: async () => {
          try {
            return await formatLocalSkills();
          } catch (error) {
            return `Error listing local SkillNet skills: ${error.message}`;
          }
        }
      },
      skillnet_search: {
        description: "Search SkillNet by keyword and return matching skills.",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string" },
            category: { type: "string" },
            limit: { type: "integer" },
            page: { type: "integer" },
            min_stars: { type: "integer" },
            sort_by: { type: "string", enum: ["stars", "recent"] }
          },
          required: ["query"]
        },
        execute: async (args) => {
          try {
            const result = await searchSkillNet({
              q: args.query,
              mode: "keyword",
              category: args.category,
              limit: args.limit ?? 10,
              page: args.page ?? 1,
              min_stars: args.min_stars ?? 0,
              sort_by: args.sort_by ?? "stars"
            });

            return formatRemoteSkills(result.data, result.meta);
          } catch (error) {
            return `Error searching SkillNet: ${error.message}`;
          }
        }
      },
      skillnet_semantic_search: {
        description: "Search SkillNet semantically from a natural language request.",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string" },
            category: { type: "string" },
            limit: { type: "integer" },
            threshold: { type: "number" }
          },
          required: ["query"]
        },
        execute: async (args) => {
          try {
            const result = await searchSkillNet({
              q: args.query,
              mode: "vector",
              category: args.category,
              limit: args.limit ?? 10,
              threshold: args.threshold ?? 0.8
            });

            return formatRemoteSkills(result.data, result.meta);
          } catch (error) {
            return `Error with SkillNet semantic search: ${error.message}`;
          }
        }
      }
    }
  };
};

export default SkillNetPlugin;
