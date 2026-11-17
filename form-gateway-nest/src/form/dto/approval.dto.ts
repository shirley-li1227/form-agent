import { IsBoolean, IsOptional, IsString } from 'class-validator';

export class ApprovalDto {
  @IsBoolean()
  approved: boolean;

  @IsOptional()
  @IsString()
  comment?: string;
}
