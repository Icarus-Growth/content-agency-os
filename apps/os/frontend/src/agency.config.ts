/* What this agency is: a content agency.
 *
 * The boards, their stage ladders, the fields on a card, the agency's own columns on the client
 * page and the weekly numbers. Change a stage here AND in the database, then run
 * `python3 tests/config_matches_db.py`. */
import type { AgencyConfig, Ladders } from './config';

/** The agency's own database lists. They must match the migrations exactly. */
export const LADDERS = {
  video_stage: [
    '0 - Raw Footage',
    '10 - Ready To Edit',
    '20 - Editing',
    '30 - Internal Review',
    '39 - Amendments',
    '40 - Client Review',
    '49 - Client Changes',
    '50 - Ready To Post',
    '60 - Scheduled',
    '100 - Posted',
  ],
  caption_status: ['To Write', 'To Review', 'Done'],
} as const satisfies Ladders;

export const AGENCY: AgencyConfig = {
  agency: 'Content',
  boards: [
    {
      table: 'videos',
      label: 'Editing pipeline',
      item: 'video',
      desc: 'One card is one video for one client, from raw footage to posted.',
      nameKey: 'video_title',
      stageKey: 'stage',
      ladder: 'video_stage',
      closed: ['60 - Scheduled', '100 - Posted'],
      clientRequired: true,
      card: ['client_id', 'assignee_id', 'due_date'],
      sections: [
        { title: 'Basic details', desc: 'What the video is, for which client, and who works on it.', fields: [
          { key: 'video_title', label: 'Video', type: 'text', required: true },
          { key: 'client_id', label: 'Client', type: 'client', required: true },
          { key: 'assignee_id', label: 'Assignee', type: 'person', desc: 'Who must act now: usually the editor.' },
          { key: 'reviewer_id', label: 'Reviewer', type: 'person', desc: 'Who checks the edit before the client sees it.' },
          { key: 'platform', label: 'Platform', type: 'text' },
        ] },
        { title: 'Edit', desc: 'For the editor: the raw footage, the finished cut and the deadline.', fields: [
          { key: 'due_date', label: 'Due date', type: 'date' },
          { key: 'raw_footage_url', label: 'Raw footage', type: 'url' },
          { key: 'edited_url', label: 'Finished cut', type: 'url' },
        ] },
        { title: 'Caption', desc: 'For the social media manager: the caption and its status.', fields: [
          { key: 'caption_status', label: 'Caption status', type: 'choice', list: 'caption_status' },
          { key: 'caption', label: 'Caption', type: 'document', check: 'caption', desc: 'Checked against the limit of the platform on this card.' },
        ] },
        { title: 'Posting', desc: 'When it goes out and where to find it.', fields: [
          { key: 'scheduled_for', label: 'Scheduled for', type: 'datetime' },
          { key: 'posted_at', label: 'Posted at', type: 'datetime' },
          { key: 'post_url', label: 'Post', type: 'url' },
        ] },
        { title: 'Feedback and notes', desc: 'What the reviewer or the client asked to change.', fields: [
          { key: 'feedback_notes', label: 'Feedback', type: 'longtext' },
          { key: 'notes', label: 'Notes', type: 'longtext' },
        ] },
      ],
      create: ['video_title', 'client_id', 'assignee_id', 'due_date'],
    },
  ],
  lists: [],
  clientSections: [
    { title: 'People', desc: 'Who looks after this client in each role.', fields: [
      { key: 'account_manager_id', label: 'Account manager', type: 'person' },
      { key: 'editor_id', label: 'Editor', type: 'person' },
      { key: 'social_media_manager_id', label: 'Social media manager', type: 'person' },
    ] },
    { title: 'Content', desc: 'Where the client posts and what the team works from.', fields: [
      { key: 'platforms', label: 'Platforms', type: 'tags', desc: 'Where the client posts, separated by commas.' },
      { key: 'posts_per_week', label: 'Posts per week', type: 'int' },
      { key: 'raw_footage_folder_url', label: 'Raw footage folder', type: 'url', desc: 'Where the client uploads raw footage.' },
      { key: 'brand_guidelines_url', label: 'Brand guidelines', type: 'url' },
      { key: 'strategy_brief', label: 'Strategy brief', type: 'document', link: 'strategy_brief_url' },
    ] },
  ],
  metrics: [
    { key: 'posts_published', label: 'Posts published', format: 'int' },
    { key: 'views', label: 'Views', format: 'int' },
    { key: 'followers', label: 'Followers', format: 'int' },
    { key: 'engagement_rate', label: 'Engagement rate', format: 'percent' },
    { key: 'top_post_url', label: 'Top post', format: 'url' },
  ],
};
