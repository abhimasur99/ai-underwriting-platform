// What the reviewer's chat suggests before anything has been asked. A question is sent as it is;
// an edit is only filled into the box, because it needs the reviewer's own numbers and reason.
export interface Prompt {
  text: string
  send: boolean
}

export const REVIEWER_PROMPTS: Prompt[] = [
  { text: 'Summarize this deal', send: true },
  { text: 'What are the exceptions?', send: true },
  { text: 'Why is the call what it is?', send: true },
  { text: 'What changed in this version?', send: true },
  { text: 'Change the ARV to 11,000,000 because the appraisal came in lower', send: false },
  { text: 'Change unit 101 rent to 2,100 because the signed lease shows 2,100', send: false },
]
