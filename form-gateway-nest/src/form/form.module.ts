import { Module } from '@nestjs/common';
import { AppConfigService } from '../config/config.service';
import { FormController } from './form.controller';
import { FormService } from './form.service';

@Module({
  controllers: [FormController],
  providers: [FormService, AppConfigService],
})
export class FormModule {}
