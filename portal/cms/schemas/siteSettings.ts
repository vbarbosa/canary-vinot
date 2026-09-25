import { defineType, defineField, defineArrayMember } from "sanity";

export const siteSettings = defineType({
  name: "siteSettings",
  title: "Configurações do site",
  type: "document",
  fields: [
    defineField({ name: "serverName", title: "Nome do servidor", type: "string", initialValue: "VinOT" }),
    defineField({ name: "tagline", title: "Frase curta", type: "string", validation: (r) => r.max(100) }),
    defineField({
      name: "notice",
      title: "Aviso no topo do site",
      type: "string",
      description: "Faixa vermelha em todas as páginas. Deixe vazio pra esconder.",
      validation: (r) => r.max(160),
    }),
    defineField({ name: "clientAndroidUrl", title: "Link do cliente Android (APK)", type: "url" }),
    defineField({ name: "clientWindowsUrl", title: "Link do cliente Windows", type: "url" }),
    defineField({ name: "whatsappUrl", title: "Grupo do WhatsApp", type: "url" }),
    defineField({ name: "instagramUrl", title: "Instagram", type: "url" }),
    defineField({
      name: "howToPlay",
      title: "Passos do \"Como jogar\"",
      type: "array",
      of: [defineArrayMember({ type: "string" })],
      validation: (r) => r.max(6),
    }),
  ],
  preview: { prepare: () => ({ title: "Configurações do site" }) },
});
