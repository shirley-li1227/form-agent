import { Body, Controller, Get, Param, Post } from '@nestjs/common';
import { ApprovalDto } from './dto/approval.dto';
import { GenerateFormDto } from './dto/generate-form.dto';
import { FormService } from './form.service';

@Controller('api/form')
export class FormController {
  constructor(private readonly formService: FormService) {}

  @Post('generate')
  async generate(@Body() dto: GenerateFormDto) {
    return this.formService.generateForm(dto);
  }

  @Get('run/:runId')
  async getRun(@Param('runId') runId: string) {
    return this.formService.getRun(runId);
  }

  @Post('approval/:runId')
  async approval(@Param('runId') runId: string, @Body() dto: ApprovalDto) {
    return this.formService.approval(runId, dto);
  }
}
