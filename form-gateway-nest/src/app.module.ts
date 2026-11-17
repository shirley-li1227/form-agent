import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { AppConfigService } from './config/config.service';
import { FormModule } from './form/form.module';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), FormModule],
  providers: [AppConfigService],
})
export class AppModule {}
