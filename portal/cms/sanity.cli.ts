import { defineCliConfig } from "sanity/cli";

export default defineCliConfig({
  api: {
    projectId: process.env.SANITY_STUDIO_PROJECT_ID || "TROCAR",
    dataset: "production",
  },
  // Studio hospedado em https://vinot.sanity.studio (rode `npm run deploy`).
  studioHost: "vinot",
});
