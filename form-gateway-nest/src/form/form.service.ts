import { HttpException, HttpStatus, Injectable, Logger } from '@nestjs/common';
import axios, { AxiosError } from 'axios';
import { AppConfigService } from '../config/config.service';
import { ApprovalDto } from './dto/approval.dto';
import { GenerateFormDto } from './dto/generate-form.dto';

@Injectable()
export class FormService {
  private readonly logger = new Logger(FormService.name);

  constructor(private readonly config: AppConfigService) {}

  private get baseUrl(): string {
    return this.config.aiAgentBaseUrl;
  }

  async generateForm(dto: GenerateFormDto) {
    return this.request(() =>
      axios.post(
        `${this.baseUrl}/api/form/generate`,
        {
          requirement: dto.requirement,
          need_approval: dto.need_approval ?? true,
        },
        { timeout: this.config.timeout },
      ),
    );
  }

  async getRun(runId: string) {
    return this.request(() =>
      axios.get(`${this.baseUrl}/api/form/run/${runId}`, {
        timeout: this.config.timeout,
      }),
    );
  }

  async approval(runId: string, dto: ApprovalDto) {
    return this.request(() =>
      axios.post(
        `${this.baseUrl}/api/form/approval/${runId}`,
        { approved: dto.approved, comment: dto.comment },
        { timeout: this.config.timeout },
      ),
    );
  }

  /** 统一转发并把上游错误转成网关错误，避免前端拿到裸 500。 */
  private async request<T>(send: () => Promise<{ data: T }>): Promise<T> {
    try {
      const res = await send();
      return res.data;
    } catch (err) {
      const axiosError = err as AxiosError<{ detail?: string }>;
      const status = axiosError.response?.status ?? HttpStatus.BAD_GATEWAY;
      const detail =
        axiosError.response?.data?.detail ??
        (status === HttpStatus.BAD_GATEWAY
          ? `无法连接 AI 服务 ${this.baseUrl}`
          : axiosError.message);
      this.logger.error(`AI 服务调用失败 ${status}: ${detail}`);
      throw new HttpException({ code: status, message: detail }, status);
    }
  }
}
