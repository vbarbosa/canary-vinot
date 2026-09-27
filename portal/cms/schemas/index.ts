import { post } from "./post";
import { homePage } from "./homePage";
import { siteSettings } from "./siteSettings";
import { videoEmbed } from "./videoEmbed";

export const schemaTypes = [post, homePage, siteSettings, videoEmbed];

// Documentos de instância única (sem "criar novo").
export const singletonTypes = new Set(["homePage", "siteSettings"]);
