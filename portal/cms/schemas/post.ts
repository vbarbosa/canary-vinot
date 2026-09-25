import { defineType, defineField, defineArrayMember } from "sanity";

// Notícia, atualização, evento ou promoção. O portal mostra as mais recentes na página
// inicial; promoções e eventos com "Termina em" no futuro aparecem na faixa de destaque.

export const post = defineType({
  name: "post",
  title: "Notícia / Promoção",
  type: "document",
  fields: [
    defineField({ name: "title", title: "Título", type: "string", validation: (r) => r.required().max(90) }),
    defineField({
      name: "slug",
      title: "Endereço (URL)",
      type: "slug",
      description: "Gerado a partir do título.",
      options: { source: "title", maxLength: 96 },
      validation: (r) => r.required(),
    }),
    defineField({
      name: "category",
      title: "Tipo",
      type: "string",
      options: {
        list: [
          { title: "Notícia", value: "noticia" },
          { title: "Atualização", value: "atualizacao" },
          { title: "Evento", value: "evento" },
          { title: "Promoção", value: "promocao" },
        ],
        layout: "radio",
        direction: "horizontal",
      },
      initialValue: "noticia",
      validation: (r) => r.required(),
    }),
    defineField({
      name: "publishedAt",
      title: "Publicar em",
      type: "datetime",
      description: "Só aparece no site a partir desta data.",
      initialValue: () => new Date().toISOString(),
      validation: (r) => r.required(),
    }),
    defineField({
      name: "endsAt",
      title: "Termina em",
      type: "datetime",
      description: "Pra eventos e promoções: some da faixa de destaque depois disso.",
      hidden: ({ document }) => !["evento", "promocao"].includes(String(document?.category)),
    }),
    defineField({ name: "featured", title: "Destaque", type: "boolean", description: "Fica no topo da lista.", initialValue: false }),
    defineField({ name: "excerpt", title: "Resumo", type: "text", rows: 3, validation: (r) => r.max(220) }),
    defineField({ name: "cover", title: "Imagem de capa", type: "image", options: { hotspot: true } }),
    defineField({
      name: "body",
      title: "Texto",
      type: "array",
      of: [
        defineArrayMember({
          type: "block",
          styles: [
            { title: "Normal", value: "normal" },
            { title: "Título", value: "h2" },
            { title: "Subtítulo", value: "h3" },
            { title: "Citação", value: "blockquote" },
          ],
          lists: [
            { title: "Lista", value: "bullet" },
            { title: "Numerada", value: "number" },
          ],
          marks: {
            decorators: [
              { title: "Negrito", value: "strong" },
              { title: "Itálico", value: "em" },
              { title: "Sublinhado", value: "underline" },
            ],
            annotations: [
              {
                name: "link",
                type: "object",
                title: "Link",
                fields: [{ name: "href", type: "url", title: "URL", validation: (r) => r.uri({ scheme: ["http", "https", "mailto"] }) }],
              },
            ],
          },
        }),
        defineArrayMember({
          type: "image",
          options: { hotspot: true },
          fields: [
            { name: "alt", type: "string", title: "Descrição da imagem" },
            { name: "caption", type: "string", title: "Legenda" },
          ],
        }),
        defineArrayMember({ type: "videoEmbed" }),
      ],
    }),
    defineField({
      name: "cta",
      title: "Botão no fim do post",
      type: "object",
      options: { collapsible: true, collapsed: true },
      fields: [
        { name: "label", type: "string", title: "Texto do botão" },
        { name: "url", type: "url", title: "Link", validation: (r) => r.uri({ allowRelative: true, scheme: ["http", "https"] }) },
      ],
    }),
  ],
  orderings: [{ title: "Mais recentes", name: "recent", by: [{ field: "publishedAt", direction: "desc" }] }],
  preview: {
    select: { title: "title", category: "category", date: "publishedAt", media: "cover" },
    prepare: ({ title, category, date, media }) => ({
      title,
      subtitle: `${{ noticia: "Notícia", atualizacao: "Atualização", evento: "Evento", promocao: "Promoção" }[category as string] || ""} · ${date ? new Date(date).toLocaleDateString("pt-BR") : "rascunho"}`,
      media,
    }),
  },
});
