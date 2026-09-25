import { defineType, defineField } from "sanity";

export const videoEmbed = defineType({
  name: "videoEmbed",
  title: "Vídeo do YouTube",
  type: "object",
  fields: [
    defineField({
      name: "url",
      title: "Link do vídeo",
      type: "url",
      validation: (rule) => rule.required().uri({ scheme: ["https"] }),
    }),
  ],
  preview: { select: { title: "url" }, prepare: ({ title }) => ({ title: "Vídeo", subtitle: title }) },
});
