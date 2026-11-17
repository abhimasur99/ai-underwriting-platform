// Convenience for the demo: the facts a sponsor would type for each sample deal. The chat reads
// them like any other message; nothing here bypasses the checklist.
export const SAMPLE_FACTS = [
  {
    label: 'Bronx facts',
    folder: 'data/deals/bronx_mf',
    text:
      'Sponsor is Harborline Residential LLC. Address: 1200 Sample Avenue, Bronx, NY 10456. ' +
      '40 units, multifamily. Purchase price $8,000,000, reno budget $1,200,000, ' +
      'loan amount $6,500,000',
  },
  {
    label: 'Queens facts',
    folder: 'data/deals/queens_mixed_use',
    text:
      'Sponsor is Harborline Residential LLC. Address: 47-10 Sample Boulevard, Queens, NY 11101. ' +
      '20 units, mixed use. Purchase price $5,000,000, reno budget $800,000, ' +
      'loan amount $4,300,000',
  },
  {
    label: 'Brooklyn facts',
    folder: 'data/deals/overleveraged_bk',
    text:
      'Sponsor is Harborline Residential LLC. Address: 310 Sample Street, Brooklyn, NY 11216. ' +
      '22 units, multifamily. Purchase price $4,000,000, reno budget $600,000, ' +
      'loan amount $4,050,000',
  },
]

export const REVIEWER_PROMPTS = [
  'Why is this call what it is?',
  'What is the exit DSCR?',
  'What does the stress case show?',
  'Change the ARV to 11,000,000 because the appraisal came in lower',
  'Change unit 101 rent to 2,100 because the signed lease shows 2,100',
  'Override: comfortable with the sponsor track record because six prior renovations closed on time',
]
