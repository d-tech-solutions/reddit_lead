// Starter watchers for the create form. Each one is a complete, editable draft — picking it fills
// the form, it never creates anything on its own.
//
// Intents are written the way the verifier reads them: who the poster is, what they want, and which
// direction the request runs (someone *seeking* the service, not offering it). Subreddits are kept
// to a few real, busy ones, since every extra subreddit counts against the plan's pool.

export interface WatcherTemplate {
  id: string;
  label: string;
  name: string;
  intent_text: string;
  subreddits: string[];
}

export const WATCHER_TEMPLATES: WatcherTemplate[] = [
  {
    id: "wordpress",
    label: "WordPress",
    name: "WordPress help wanted",
    intent_text:
      "Someone looking to hire a WordPress developer to build, customise or fix a WordPress site, theme or plugin. Not people offering their own WordPress services.",
    subreddits: ["forhire", "hiring", "wordpress", "slavelabour"],
  },
  {
    id: "web-dev",
    label: "Web development",
    name: "Web developer wanted",
    intent_text:
      "Someone asking to hire a web developer or freelancer to build or fix a website or web app, paid work only. Ignore developers advertising themselves and people asking for free help.",
    subreddits: ["forhire", "hiring", "webdev", "slavelabour"],
  },
  {
    id: "design",
    label: "Graphic design",
    name: "Design work wanted",
    intent_text:
      "Someone looking to hire a graphic designer for a logo, branding, social media graphics or other design work. Not designers offering their portfolio or services.",
    subreddits: ["forhire", "hiring", "graphic_design", "logodesign"],
  },
  {
    id: "copywriting",
    label: "Copywriting",
    name: "Writers wanted",
    intent_text:
      "Someone looking to hire a copywriter or content writer for website copy, blog posts, emails or ads. Not writers advertising their own services.",
    subreddits: ["forhire", "hiring", "copywriting", "slavelabour"],
  },
  {
    id: "video-editing",
    label: "Video editing",
    name: "Video editor wanted",
    intent_text:
      "Someone looking to hire a video editor for YouTube videos, short-form clips, ads or other footage. Not editors offering their services.",
    subreddits: ["forhire", "hiring", "videoediting", "youtubers"],
  },
  {
    id: "marketing",
    label: "Marketing",
    name: "Marketing help wanted",
    intent_text:
      "Someone looking to hire a marketer, SEO specialist, ads manager or social media manager to grow their business. Not agencies or freelancers advertising themselves.",
    subreddits: ["forhire", "hiring", "marketing", "entrepreneur"],
  },
  {
    id: "app-dev",
    label: "App development",
    name: "App developer wanted",
    intent_text:
      "Someone looking to hire a developer to build a mobile app, MVP or software product, or asking where to find a technical cofounder. Not developers offering their services.",
    subreddits: ["forhire", "hiring", "startups", "entrepreneur"],
  },
  {
    id: "virtual-assistant",
    label: "Virtual assistant",
    name: "Assistant wanted",
    intent_text:
      "Someone looking to hire a virtual assistant, admin helper or data-entry freelancer for ongoing or one-off tasks. Not people offering assistant services.",
    subreddits: ["forhire", "hiring", "virtualassistant", "slavelabour"],
  },
];
