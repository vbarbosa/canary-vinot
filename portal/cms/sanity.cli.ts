import { defineCliConfig } from "sanity/cli";

export default defineCliConfig({
  api: {
    projectId: process.env.SANITY_STUDIO_PROJECT_ID || "uh4swsqs",
    dataset: "production",
  },
  // Studio hospedado em https://vinot.sanity.studio (rode `npm run deploy`).
  studioHost: "vinot",
});
