import { defineConfig } from "sanity";
import { structureTool } from "sanity/structure";
import { visionTool } from "@sanity/vision";
import { schemaTypes, singletonTypes } from "./schemas";

// Painel de conteúdo do portal VinOT (mesmo modelo do CMS do Manchete).
// projectId e dataset são públicos: o portal lê o conteúdo publicado sem token.
// O Studio em si é protegido pelo login do Sanity; só quem você convidar edita.

const SINGLETONS = [
  { id: "siteSettings", title: "Configurações do site" },
  { id: "homePage", title: "Página inicial" },
] as const;

export default defineConfig({
  name: "vinot",
  title: "VinOT — Conteúdo",
  projectId: process.env.SANITY_STUDIO_PROJECT_ID || "TROCAR",
  dataset: "production",

  plugins: [
    structureTool({
      structure: (S) =>
        S.list()
          .title("Conteúdo")
          .items([
            ...SINGLETONS.map((s) =>
              S.listItem().title(s.title).id(s.id).child(S.document().schemaType(s.id).documentId(s.id)),
            ),
            S.divider(),
            S.listItem().title("Notícias e promoções").child(S.documentTypeList("post").title("Notícias e promoções")),
          ]),
    }),
    visionTool(),
  ],

  schema: {
    types: schemaTypes,
    templates: (templates) => templates.filter(({ schemaType }) => !singletonTypes.has(schemaType)),
  },

  document: {
    actions: (input, context) =>
      singletonTypes.has(context.schemaType)
        ? input.filter(({ action }) => action && ["publish", "discardChanges", "restore"].includes(action))
        : input,
  },
});
