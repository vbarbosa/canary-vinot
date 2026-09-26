import { defineType, defineField, defineArrayMember } from "sanity";
import { PIXEL_ICONS } from "./icons";

export const homePage = defineType({
  name: "homePage",
  title: "Página inicial",
  type: "document",
  fields: [
    defineField({ name: "heroTitle", title: "Título grande", type: "string", validation: (r) => r.max(60) }),
    defineField({ name: "heroText", title: "Texto de boas-vindas", type: "text", rows: 3, validation: (r) => r.max(260) }),
    defineField({ name: "ctaText", title: "Texto do botão de cadastro", type: "string", initialValue: "Criar minha conta" }),
    defineField({
      name: "features",
      title: "Destaques (\"O que tem no VinOT\")",
      type: "array",
      validation: (r) => r.max(8),
      of: [
        defineArrayMember({
          type: "object",
          fields: [
            { name: "icon", title: "Ícone", type: "string", options: { list: PIXEL_ICONS } },
            { name: "title", title: "Título", type: "string", validation: (r) => r.required().max(40) },
            { name: "text", title: "Texto", type: "text", rows: 2, validation: (r) => r.max(140) },
          ],
          preview: { select: { title: "title", subtitle: "text" } },
        }),
      ],
    }),
  ],
  preview: { prepare: () => ({ title: "Página inicial" }) },
});
