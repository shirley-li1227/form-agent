import { Injectable } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';

@Injectable()
export class AppConfigService {
  constructor(private readonly configService: ConfigService) {}

  get aiAgentBaseUrl(): string {
    return (
      this.configService.get<string>('AI_AGENT_BASE_URL') ?? 'http://127.0.0.1:8000'
    );
  }

  get timeout(): number {
    return Number(this.configService.get('AI_AGENT_TIMEOUT_MS')) || 30000;
  }

  get port(): number {
    return Number(this.configService.get('PORT')) || 3000;
  }
}
