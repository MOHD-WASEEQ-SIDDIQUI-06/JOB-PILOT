export const mockJobResults = [
  {
    id: 'job-1',
    title: 'Python Backend Developer',
    company: 'Acme Labs',
    location: 'Bangalore',
    match_score: 92,
    matching_skills: ['Python', 'FastAPI', 'PostgreSQL'],
    missing_skills: ['Docker'],
    recommendation: 'strong_match',
    explanation: 'Strong alignment with the core backend responsibilities and stack.',
  },
  {
    id: 'job-2',
    title: 'Frontend Engineer',
    company: 'Nova Systems',
    location: 'Remote',
    match_score: 42,
    matching_skills: ['React'],
    missing_skills: ['TypeScript', 'CSS'],
    recommendation: 'low_match',
    explanation: 'This role does not align strongly with the candidate profile.',
  },
];
